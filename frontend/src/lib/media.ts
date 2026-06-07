const FALLBACK_DATA_URL =
  "data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs=";

const bucket = process.env.NEXT_PUBLIC_MINIO_BUCKET ?? "images";
const minioBaseUrl =
  process.env.NEXT_PUBLIC_MINIO_URL ?? "http://localhost:9000";
const apiBaseUrl = (
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
).replace(/\/+$/, "");

export const MINIO_URL_STALE_TIME_MS = 1000 * 60 * 45; // 45 minutes
export const MINIO_URL_REFRESH_INTERVAL_MS = 1000 * 60 * 50; // 50 minutes

function buildEncodedUrl(objectKey?: string | null) {
  if (!objectKey) {
    return null;
  }

  const sanitizedBase = minioBaseUrl.endsWith("/")
    ? minioBaseUrl.slice(0, -1)
    : minioBaseUrl;

  const encodedKey = objectKey
    .split("/")
    .map((segment) => encodeURIComponent(segment))
    .join("/");

  return `${sanitizedBase}/${bucket}/${encodedKey}`;
}

export function resolveMediaUrl(
  url?: string | null,
  objectKey?: string | null,
  id?: number | null,
  isThumbnail: boolean = false,
) {
  if (url?.startsWith("/api/")) {
    return `${apiBaseUrl}${url}`;
  }

  if (isThumbnail && id != null) {
    return `${apiBaseUrl}/api/image/${id}/thumbnail`;
  }

  const fallback = buildEncodedUrl(objectKey);

  if (url?.includes("X-Amz-Signature=")) {
    return url;
  }

  return fallback ?? url;
}

export function getFallbackImageUrl() {
  return FALLBACK_DATA_URL;
}
