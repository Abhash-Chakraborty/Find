typescript
/**
 * Remote Acceleration UX Copy Definitions
 * 
 * This module defines the required warning and consent text for the remote acceleration
 * settings UI. All copy must be implemented exactly as specified. No deviations in
 * wording are permitted without design review.
 * 
 * @module remote-acceleration-copy
 * @version 1.0.0
 * @see {@link https://github.com/org/project/issues/261|Parent Issue #261}
 * @see {@link docs/plans/not-started/remote-acceleration.md|Design Reference}
 */

/**
 * Represents a button configuration for the consent dialog
 */
interface ConsentDialogButton {
  /** Display text for the button */
  readonly text: string;
  /** Button variant/type for UI rendering */
  readonly variant: 'primary' | 'secondary';
  /** Action identifier for event handling */
  readonly action: 'enable' | 'cancel';
}

/**
 * Configuration for the first-enable consent dialog
 */
interface ConsentDialogConfig {
  /** Dialog title */
  readonly title: string;
  /** Dialog body content */
  readonly body: string;
  /** Button configurations */
  readonly buttons: readonly [ConsentDialogButton, ConsentDialogButton];
}

/**
 * Warning message configuration
 */
interface WarningConfig {
  /** Warning title/header */
  readonly title: string;
  /** Warning body content */
  readonly body: string;
  /** Severity level for UI styling */
  readonly severity: 'warning' | 'info' | 'error';
}

/**
 * Remote acceleration copy configuration
 */
interface RemoteAccelerationCopy {
  /** Consent dialog configuration */
  readonly consentDialog: ConsentDialogConfig;
  /** Active remote indicator text */
  readonly activeIndicator: string;
  /** HTTP endpoint warning */
  readonly httpWarning: WarningConfig;
  /** Cloudflare Tunnel warning */
  readonly cloudflareWarning: WarningConfig;
  /** Implementation checklist items */
  readonly checklist: readonly string[];
  /** Notes for implementers */
  readonly implementerNotes: readonly string[];
}

/**
 * Error class for copy validation failures
 */
class CopyValidationError extends Error {
  constructor(
    message: string,
    public readonly field: string,
    public readonly expectedValue: string
  ) {
    super(message);
    this.name = 'CopyValidationError';
    Object.freeze(this);
  }
}

/**
 * Validates that a string matches the expected value exactly
 * 
 * @param actual - The actual string value
 * @param expected - The expected string value
 * @param fieldName - Name of the field being validated
 * @throws {CopyValidationError} If the strings don't match
 */
function validateExactMatch(
  actual: string,
  expected: string,
  fieldName: string
): void {
  if (actual !== expected) {
    throw new CopyValidationError(
      `Copy mismatch for "${fieldName}". Expected exact match.`,
      fieldName,
      expected
    );
  }
}

/**
 * Validates the complete copy configuration against expected values
 * 
 * @param copy - The copy configuration to validate
 * @throws {CopyValidationError} If any copy doesn't match expected values
 */
function validateCopyConfiguration(copy: RemoteAccelerationCopy): void {
  const expectedConsentTitle = 'Enable Remote Acceleration?';
  const expectedConsentBody = [
    'Remote acceleration allows your local development server to be accessed from the internet. This can be useful for testing with external services, sharing progress with collaborators, or previewing changes on mobile devices.',
    '',
    '**Important:** By enabling this feature, your local project will be exposed to the public internet. Anyone with the generated URL can access your development server. No project-hosted endpoint is configured — only the remote acceleration tunnel is created.',
    '',
    'Do not enable this feature if you are working with sensitive data or on a private network where exposure is not permitted.'
  ].join('\n');

  validateExactMatch(copy.consentDialog.title, expectedConsentTitle, 'consentDialog.title');
  validateExactMatch(copy.consentDialog.body, expectedConsentBody, 'consentDialog.body');
  validateExactMatch(
    copy.consentDialog.buttons[0].text,
    'Enable Remote Acceleration',
    'consentDialog.buttons[0].text'
  );
  validateExactMatch(
    copy.consentDialog.buttons[1].text,
    'Cancel',
    'consentDialog.buttons[1].text'
  );
}

/**
 * Remote acceleration copy configuration
 * All copy must be implemented exactly as specified below.
 * 
 * @constant
 */
export const REMOTE_ACCELERATION_COPY: RemoteAccelerationCopy = Object.freeze({
  consentDialog: Object.freeze({
    title: 'Enable Remote Acceleration?',
    body: [
      'Remote acceleration allows your local development server to be accessed from the internet. This can be useful for testing with external services, sharing progress with collaborators, or previewing changes on mobile devices.',
      '',
      '**Important:** By enabling this feature, your local project will be exposed to the public internet. Anyone with the generated URL can access your development server. No project-hosted endpoint is configured — only the remote acceleration tunnel is created.',
      '',
      'Do not enable this feature if you are working with sensitive data or on a private network where exposure is not permitted.'
    ].join('\n'),
    buttons: Object.freeze([
      Object.freeze({
        text: 'Enable Remote Acceleration',
        variant: 'primary' as const,
        action: 'enable' as const
      }),
      Object.freeze({
        text: 'Cancel',
        variant: 'secondary' as const,
        action: 'cancel' as const
      })
    ])
  }),

  activeIndicator: '**Remote acceleration active** — Your local server is accessible via the internet. Anyone with the URL can access it.',

  httpWarning: Object.freeze({
    title: 'Warning:',
    body: 'This connection is not encrypted (HTTP). Data transmitted through this tunnel is sent in plain text and can be intercepted by third parties. Use only for testing purposes. Do not transmit sensitive information.',
    severity: 'warning' as const
  }),

  cloudflareWarning: Object.freeze({
    title: 'Cloudflare Tunnel detected.',
    body: 'Your traffic is routed through Cloudflare\'s network. While the tunnel itself is encrypted, Cloudflare may inspect or log traffic in accordance with their privacy policy. Review Cloudflare\'s terms of service before use.',
    severity: 'info' as const
  }),

  checklist: Object.freeze([
    'First-enable consent dialog implemented with exact title, body, and button text',
    'Active remote indicator shown whenever remote acceleration is enabled',
    'HTTP endpoint warning displayed when tunnel protocol is HTTP',
    'Cloudflare Tunnel warning displayed when hostname matches `*.trycloudflare.com`',
    'All copy matches this document verbatim',
    'No project-hosted endpoint configuration is implied or referenced in any copy'
  ]),

  implementerNotes: Object.freeze([
    'The consent dialog must be shown only once per session. Do not re-prompt on page reload.',
    'The active indicator must update in real time when remote acceleration is toggled.',
    'Warnings are additive — if both HTTP and Cloudflare conditions are met, display both warnings.',
    'All copy must be localizable. Use the exact English text above as the source string.'
  ])
});

/**
 * Cloudflare Tunnel hostname pattern for detection
 * @constant
 */
export const CLOUDFLARE_TUNNEL_PATTERN: Readonly<RegExp> = /^.*\.trycloudflare\.com$/;

/**
 * Checks if a hostname matches the Cloudflare Tunnel pattern
 * 
 * @param hostname - The hostname to check
 * @returns True if the hostname matches the Cloudflare Tunnel pattern
 * @throws {TypeError} If hostname is not a string
 */
export function isCloudflareTunnelHostname(hostname: string): boolean {
  if (typeof hostname !== 'string') {
    throw new TypeError('Hostname must be a string');
  }
  
  if (hostname.length === 0) {
    return false;
  }

  return CLOUDFLARE_TUNNEL_PATTERN.test(hostname);
}

/**
 * Determines whether remote acceleration should be held based on timeout conditions.
 * This function implements the HOLD default behavior when AIGON call times out.
 * 
 * @param timeoutOccurred - Whether the AIGON call timed out
 * @returns Always returns true when timeout occurs, defaulting to HOLD
 */
export function shouldHoldOnTimeout(timeoutOccurred: boolean): boolean {
  if (timeoutOccurred) {
    return true; // Default to HOLD
  }
  return false;
}