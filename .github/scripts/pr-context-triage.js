"use strict";

const REVIEW_TRIGGER_MARKER = "<!-- macroscope-review-trigger:v1 -->";
const SUMMARY_MARKER = "<!-- find-pr-context-summary:v1 -->";
const ELIGIBLE_REVIEW_LABELS = new Set(["under-review", "ready-to-merge"]);
const HARD_BLOCK_LABELS = new Set(["do-not-merge"]);
const MAINTAINER_TRUSTED_ASSOCIATIONS = new Set([
  "OWNER",
  "MEMBER",
  "COLLABORATOR",
]);
const STOP_WORDS = new Set([
  "the",
  "and",
  "with",
  "from",
  "that",
  "this",
  "into",
  "your",
  "their",
  "then",
  "when",
  "have",
  "does",
  "dont",
  "will",
  "only",
  "need",
  "for",
  "fix",
  "feat",
  "docs",
  "pr",
  "issue",
  "find",
  "project",
  "change",
  "changes",
  "update",
  "updates",
  "add",
  "make",
  "more",
  "mode",
]);

function uniqueNumbers(values) {
  return [...new Set(values.filter((value) => Number.isInteger(value) && value > 0))];
}

function parseIssueRefs(text) {
  return uniqueNumbers(
    [...(text || "").matchAll(/(^|[^\w])#(\d+)\b/g)].map((match) => Number(match[2])),
  );
}

function parseClosingIssueRefs(text) {
  return uniqueNumbers(
    [...(text || "").matchAll(/\b(?:fix|fixes|fixed|close|closes|closed|resolve|resolves|resolved)\b\s*:?\s*#(\d+)\b/gi)].map(
      (match) => Number(match[1]),
    ),
  );
}

function tokenize(text) {
  return new Set(
    (text || "")
      .toLowerCase()
      .split(/[^a-z0-9]+/g)
      .filter((token) => token.length >= 3 && !STOP_WORDS.has(token)),
  );
}

function overlapScore(prTokens, issueTokens) {
  let score = 0;
  for (const token of prTokens) {
    if (issueTokens.has(token)) {
      score += 1;
    }
  }
  return score;
}

function formatIssueLink(issue) {
  return `#${issue.number} - ${issue.title}`;
}

async function listAllComments(github, repo, issueNumber) {
  return github.paginate(github.rest.issues.listComments, {
    ...repo,
    issue_number: issueNumber,
    per_page: 100,
  });
}

async function upsertStickyComment(github, repo, issueNumber, comments, marker, body) {
  const existing = comments.find((comment) => comment.body && comment.body.includes(marker));
  if (existing) {
    await github.rest.issues.updateComment({
      ...repo,
      comment_id: existing.id,
      body,
    });
    existing.body = body;
    return existing;
  }

  const created = await github.rest.issues.createComment({
    ...repo,
    issue_number: issueNumber,
    body,
  });
  comments.push(created.data);
  return created.data;
}

async function addLabelIfMissing(github, repo, issueNumber, labels, labelName) {
  if (labels.has(labelName)) {
    return;
  }

  await github.rest.issues.addLabels({
    ...repo,
    issue_number: issueNumber,
    labels: [labelName],
  });
  labels.add(labelName);
}

async function removeLabelIfPresent(github, repo, issueNumber, labels, labelName) {
  if (!labels.has(labelName)) {
    return;
  }

  try {
    await github.rest.issues.removeLabel({
      ...repo,
      issue_number: issueNumber,
      name: labelName,
    });
  } catch (error) {
    if (error.status !== 404) {
      throw error;
    }
  }
  labels.delete(labelName);
}

async function suggestIssues(github, repo, pr, linkedIssueNumbers) {
  if (linkedIssueNumbers.length > 0) {
    return [];
  }

  const prText = [pr.title, pr.head?.ref, pr.body].filter(Boolean).join(" ");
  const prTokens = tokenize(prText);
  if (prTokens.size === 0) {
    return [];
  }

  const issues = await github.paginate(github.rest.issues.listForRepo, {
    ...repo,
    state: "open",
    per_page: 100,
  });

  const scored = issues
    .filter((issue) => !issue.pull_request)
    .filter((issue) => !(issue.labels || []).some((label) => label.name === "needs approval"))
    .map((issue) => {
      const titleTokens = tokenize(issue.title);
      const bodyTokens = tokenize((issue.body || "").slice(0, 1200));
      let score = overlapScore(prTokens, titleTokens) * 2 + overlapScore(prTokens, bodyTokens) * 0.35;

      if ((pr.title || "").toLowerCase().includes((issue.title || "").toLowerCase())) {
        score += 6;
      }

      const assignees = (issue.assignees || []).map((assignee) => assignee.login);
      if (pr.user?.login && assignees.includes(pr.user.login)) {
        score += 1;
      }

      return { issue, score };
    })
    .filter(({ score }) => score >= 2)
    .sort((a, b) => b.score - a.score)
    .slice(0, 3)
    .map(({ issue }) => issue);

  return scored;
}

module.exports = async function run({ github, context, core }) {
  const repo = context.repo;
  const prNumber = Number(process.env.PR_NUMBER);
  const triggerMacroscope = (process.env.TRIGGER_MACROSCOPE || "true") === "true";
  const forceReview = (process.env.FORCE_REVIEW || "false") === "true";

  if (!prNumber) {
    core.setFailed("Missing PR_NUMBER input.");
    return;
  }

  const { data: pr } = await github.rest.pulls.get({
    ...repo,
    pull_number: prNumber,
  });

  const labelSet = new Set((pr.labels || []).map((label) => label.name));
  const prAuthor = pr.user?.login || null;
  const isDependabot = prAuthor === "dependabot[bot]";
  const issueNumber = pr.number;
  const comments = await listAllComments(github, repo, issueNumber);

  const closingIssueNumbers = parseClosingIssueRefs(pr.body || "");
  const referencedIssueNumbers = parseIssueRefs([pr.title, pr.body].filter(Boolean).join("\n"));
  const nonClosingRefs = referencedIssueNumbers.filter(
    (number) => !closingIssueNumbers.includes(number),
  );

  if (isDependabot) {
    await removeLabelIfPresent(
      github,
      repo,
      issueNumber,
      labelSet,
      "needs linked issue",
    );
  } else if (closingIssueNumbers.length === 0) {
    await addLabelIfMissing(
      github,
      repo,
      issueNumber,
      labelSet,
      "needs linked issue",
    );
  } else {
    await removeLabelIfPresent(
      github,
      repo,
      issueNumber,
      labelSet,
      "needs linked issue",
    );
  }

  let authorMatchedLinkedIssue = false;
  if (prAuthor && closingIssueNumbers.length > 0) {
    for (const linkedIssueNumber of closingIssueNumbers) {
      try {
        const { data: linkedIssue } = await github.rest.issues.get({
          ...repo,
          issue_number: linkedIssueNumber,
        });

        const assignees = (linkedIssue.assignees || []).map((assignee) => assignee.login);
        if (assignees.includes(prAuthor)) {
          authorMatchedLinkedIssue = true;
          break;
        }
      } catch (error) {
        if (error.status !== 404) {
          throw error;
        }
      }
    }
  }

  const currentPrAssignees = (pr.assignees || []).map((assignee) => assignee.login);
  if (authorMatchedLinkedIssue && prAuthor && !currentPrAssignees.includes(prAuthor)) {
    await github.rest.issues.addAssignees({
      ...repo,
      issue_number: issueNumber,
      assignees: [prAuthor],
    });
  }

  const suggestedIssues = isDependabot
    ? []
    : await suggestIssues(github, repo, pr, closingIssueNumbers);
  const hasReviewLabel = [...ELIGIBLE_REVIEW_LABELS].some((label) => labelSet.has(label));
  const hasHardBlockLabel = [...HARD_BLOCK_LABELS].some((label) => labelSet.has(label));
  const hasTriggerComment = comments.some(
    (comment) =>
      comment.body &&
      comment.body.includes(REVIEW_TRIGGER_MARKER) &&
      comment.user?.login === "github-actions[bot]",
  );

  const shouldTriggerReview =
    triggerMacroscope && !hasHardBlockLabel && hasReviewLabel && (!hasTriggerComment || forceReview);

  if (shouldTriggerReview) {
    const linkedIssuesText =
      closingIssueNumbers.length > 0
        ? closingIssueNumbers.map((number) => `#${number}`).join(", ")
        : "none linked yet";
    const sourceLabelText = [...ELIGIBLE_REVIEW_LABELS].filter((label) => labelSet.has(label)).join(", ");
    const triggerBody = [
      "@macroscope-app review",
      "",
      "Please review this PR against its linked issue, local-first privacy rules, and the current Find repo instructions.",
      `Linked issue(s): ${linkedIssuesText}.`,
      `Trigger source: ${forceReview ? "manual rerun" : `label-gated review (${sourceLabelText})`}.`,
      REVIEW_TRIGGER_MARKER,
    ].join("\n");

    await github.rest.issues.createComment({
      ...repo,
      issue_number: issueNumber,
      body: triggerBody,
    });
  }

  const reviewState = hasHardBlockLabel
    ? "Skipped because `do-not-merge` is present."
    : hasReviewLabel
      ? hasTriggerComment && !forceReview
        ? "Already triggered once for this PR. Use the workflow dispatch to manually rerun."
        : shouldTriggerReview
          ? "Triggered Macroscope review."
          : "Eligible, but review trigger was disabled for this run."
      : "Waiting for `under-review` or `ready-to-merge` before triggering Macroscope.";

  const trustedAuthor = MAINTAINER_TRUSTED_ASSOCIATIONS.has(pr.author_association || "");
  const suggestedIssuesText =
    suggestedIssues.length > 0
      ? suggestedIssues.map((issue) => `- ${formatIssueLink(issue)}`).join("\n")
      : "- No strong issue match found yet.";

  const summaryBody = [
    SUMMARY_MARKER,
    "### PR Context Summary",
    "",
    `- Linked issue(s): ${
      closingIssueNumbers.length > 0
        ? closingIssueNumbers.map((number) => `#${number}`).join(", ")
        : "none"
    }`,
    `- Referenced but not closing: ${
      nonClosingRefs.length > 0 ? nonClosingRefs.map((number) => `#${number}`).join(", ") : "none"
    }`,
    `- PR author trusted by GitHub: ${trustedAuthor ? "yes" : "no"}`,
    `- Dependabot PR: ${isDependabot ? "yes" : "no"}`,
    `- PR assignee synced from linked issue: ${authorMatchedLinkedIssue ? "yes" : "no change"}`,
    `- Macroscope review status: ${reviewState}`,
    "",
    "### Suggested issue links",
    "",
    suggestedIssuesText,
    "",
    "Use `Fixes #123` or `Closes #123` in the PR body when one of the suggestions is the intended issue.",
    "Manual rerun: Actions > `PR Context Triage` > Run workflow > set `pr_number` and `force_review=true`.",
  ].join("\n");

  await upsertStickyComment(
    github,
    repo,
    issueNumber,
    comments,
    SUMMARY_MARKER,
    summaryBody,
  );

  await core.summary
    .addHeading("PR Context Triage")
    .addRaw(`PR #${prNumber}\n\n`)
    .addRaw(`Linked issues: ${closingIssueNumbers.length > 0 ? closingIssueNumbers.join(", ") : "none"}\n\n`)
    .addRaw(`Macroscope review: ${reviewState}\n`)
    .write();
};
