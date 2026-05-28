import axios, { type AxiosInstance } from "axios";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Create axios instance with proper configuration
export const api: AxiosInstance = axios.create({
  baseURL: API_URL,
  headers: {
    "Content-Type": "application/json",
  },
  timeout: 30000,
});

// Types
export type MediaStatus = "pending" | "processing" | "indexed" | "failed";
export type AnalysisStageName =
  | "object_detection"
  | "captioning"
  | "ocr"
  | "embedding";

export type AnalysisStageStatus = {
  status: "pending" | "success" | "failed";
  error: string | null;
};

export interface MediaItem {
  id: number;
  filename: string;
  minio_key: string;
  status: MediaStatus;
  created_at: string;
  processed_at?: string | null;
  width?: number | null;
  height?: number | null;
  file_size?: number | null;
  cluster_id?: number | null;
  cluster_label?: string | null;
  url?: string | null;
  thumbnail_url?: string | null;
  caption?: string;
  objects?: Array<{
    class: string;
    confidence: number;
    bbox: {
      x1: number;
      y1: number;
      x2: number;
      y2: number;
    };
  }>;
  has_text?: boolean;
  liked?: boolean;
}

export interface MediaDetail extends MediaItem {
  minio_key: string;
  file_hash: string;
  content_type?: string;
  metadata?: {
    caption?: string;
    objects?: Array<{
      class: string;
      confidence: number;
      bbox: { x1: number; y1: number; x2: number; y2: number };
    }>;
    ocr_text?: string;
    text_blocks?: Array<{
      text: string;
      confidence: number;
      bbox: { x: number; y: number; width: number; height: number };
    }>;
    stage_status?: Partial<Record<AnalysisStageName, AnalysisStageStatus>>;
  };
  exif?: Record<string, string>;
  error?: string | null;
}

export interface UploadResult {
  filename: string;
  status: "uploaded" | "duplicate" | "failed";
  media_id?: number;
  job_id?: string;
  error?: string;
}

export interface UploadResponse {
  results: UploadResult[];
  total: number;
}

export interface GalleryResponse {
  items: MediaItem[];
  total: number;
  page: number;
  skip?: number;
  limit: number;
}

export interface BulkDeleteResponse {
  message: string;
  deleted_ids: number[];
  missing_ids: number[];
  failed_ids: number[];
  deleted_count: number;
  missing_count: number;
  failed_count: number;
}

export interface DuplicatePair {
  duplicate_id: number;
  duplicate_name: string;
  original_id: number;
  original_name: string;
}

export interface DuplicatesResponse {
  total: number;
  page: number;
  limit: number;
  items: DuplicatePair[];
}

export interface ClusterSample {
  id: number;
  filename: string;
  url?: string | null;
  thumbnail_url?: string | null;
}

export interface ClusterInfo {
  id: number;
  type: string;
  label?: string | null;
  description?: string | null;
  member_count: number;
  created_at: string;
  samples: ClusterSample[];
}

export interface ClustersResponse {
  clusters: ClusterInfo[];
  total: number;
  min_cluster_size?: number;
}

export interface ClusterDetail {
  id: number;
  type: string;
  label?: string | null;
  description?: string | null;
  member_count: number;
  created_at: string;
  members: Array<{
    id: number;
    filename: string;
    url?: string | null;
    thumbnail_url?: string | null;
    caption?: string;
  }>;
}

export type ClusterUpdateResponse = Omit<ClusterInfo, "samples">;

export interface ClusteringJobResponse {
  message: string;
  job_id: string;
  status: JobStatus["status"];
  enqueued: boolean;
}

export interface SearchResult {
  media_id: number;
  similarity: number;
  metadata: MediaItem;
}

export interface SearchResponse {
  results: SearchResult[];
  total: number;
  query: string;
  page: number;
  limit: number;
  skip: number;
  has_more: boolean;
}

export interface JobStatus {
  job_id: string;
  status: "queued" | "started" | "finished" | "failed";
  stage?: string;
  created_at?: string | null;
  started_at?: string | null;
  ended_at?: string | null;
  result?: unknown;
  error?: string;
}

export interface AppConfig {
  ml_mode: "full" | "mock";
}

// API Functions
export const uploadImages = async (
  files: FileList | File[],
): Promise<UploadResponse> => {
  const formData = new FormData();

  const fileArray = files instanceof FileList ? Array.from(files) : files;
  fileArray.forEach((file) => {
    formData.append("files", file);
  });

  const response = await api.post<UploadResponse>("/api/upload", formData, {
    headers: {
      "Content-Type": "multipart/form-data",
    },
  });

  return response.data;
};

export const uploadImagesBulk = async (
  zipFile: File,
): Promise<UploadResponse> => {
  const formData = new FormData();
  formData.append("file", zipFile);

  const response = await api.post<UploadResponse>(
    "/api/upload/bulk",
    formData,
    {
      headers: {
        "Content-Type": "multipart/form-data",
      },
    },
  );

  return response.data;
};

export const getJobStatus = async (jobId: string): Promise<JobStatus> => {
  const response = await api.get<JobStatus>(`/api/status/${jobId}`);
  return response.data;
};

export const getAppConfig = async (): Promise<AppConfig> => {
  const response = await api.get<AppConfig>("/api/config");
  return response.data;
};

export const getGallery = async (
  params: {
    page?: number;
    limit?: number;
    status?: MediaStatus;
    liked?: boolean;
  } = {},
): Promise<GalleryResponse> => {
  const page = params.page || 1;
  const limit = params.limit || 50;
  const skip = (page - 1) * limit;

  const queryParams = {
    skip,
    limit,
    status: params.status,
    liked: params.liked,
  };

  const response = await api.get<GalleryResponse>("/api/gallery", {
    params: queryParams,
  });
  return response.data;
};

export const getImageDetail = async (mediaId: number): Promise<MediaDetail> => {
  const response = await api.get<MediaDetail>(`/api/image/${mediaId}`);
  return response.data;
};

export const toggleLike = async (
  mediaId: number,
): Promise<{ id: number; liked: boolean }> => {
  const response = await api.post<{ id: number; liked: boolean }>(
    `/api/image/${mediaId}/like`,
  );
  return response.data;
};

export const deleteImage = async (
  mediaId: number,
): Promise<{ id: number; message: string }> => {
  const response = await api.delete<{ id: number; message: string }>(
    `/api/image/${mediaId}`,
  );
  return response.data;
};

export const deleteImagesBulk = async (
  mediaIds: number[],
): Promise<BulkDeleteResponse> => {
  const response = await api.post<BulkDeleteResponse>(
    "/api/images/bulk-delete",
    {
      media_ids: mediaIds,
    },
  );
  return response.data;
};

export const getDuplicates = async (
  params: { page?: number; limit?: number } = {},
): Promise<DuplicatesResponse> => {
  const response = await api.get<DuplicatesResponse>("/api/duplicates", {
    params: {
      page: params.page ?? 1,
      limit: params.limit ?? 20,
    },
  });
  return response.data;
};

export const keepBothDuplicateImages = async (
  mediaId: number,
): Promise<{ status: "ok" }> => {
  const response = await api.post<{ status: "ok" }>(
    `/api/image/${mediaId}/keep`,
  );
  return response.data;
};

export const searchImages = async (params: {
  query: string;
  limit?: number;
  skip?: number;
}): Promise<SearchResponse> => {
  const response = await api.get<SearchResponse>("/api/search", {
    params: {
      q: params.query,
      limit: params.limit || 24,
      skip: params.skip || 0,
    },
  });
  return response.data;
};

export interface ReprocessResponse {
  media_id: number;
  job_id: string;
  status: "queued";
}

export const reprocessImage = async (
  mediaId: number,
): Promise<ReprocessResponse> => {
  const response = await api.post<ReprocessResponse>(
    `/api/image/${mediaId}/reprocess`,
  );
  return response.data;
};

export const getClusters = async (): Promise<ClustersResponse> => {
  const response = await api.get<ClustersResponse>("/api/clusters");
  return response.data;
};

export const getClusterDetail = async (
  clusterId: number,
): Promise<ClusterDetail> => {
  const response = await api.get<ClusterDetail>(`/api/cluster/${clusterId}`);
  return response.data;
};

export const updateCluster = async (
  clusterId: number,
  payload: { label?: string | null },
): Promise<ClusterUpdateResponse> => {
  const response = await api.patch<ClusterUpdateResponse>(
    `/api/cluster/${clusterId}`,
    payload,
  );
  return response.data;
};

export const triggerClustering = async (): Promise<ClusteringJobResponse> => {
  const response = await api.post<ClusteringJobResponse>("/api/cluster/run");
  return response.data;
};

export function extractErrorMessage(error: unknown, fallback: string): string {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data;
    if (typeof data?.detail === "string" && data.detail.trim()) {
      return data.detail.trim();
    }
    if (
      typeof data?.detail === "object" &&
      typeof data.detail?.message === "string" &&
      data.detail.message.trim()
    ) {
      return data.detail.message.trim();
    }
    if (typeof data?.message === "string" && data.message.trim()) {
      return data.message.trim();
    }
    if (typeof data?.error === "string" && data.error.trim()) {
      return data.error.trim();
    }
    if (typeof data === "string" && data.trim()) {
      return data.trim();
    }
  }
  return fallback;
}

// ─── People / Face Recognition API ───────────────────────────────────────────

export interface PersonItem {
  id: number;
  name: string | null;
  face_count: number;
  sample_media_ids: number[];
  thumbnail_url?: string | null;
}

export interface PersonImage {
  media_id: number;
  filename: string;
  thumbnail_url?: string | null;
  faces: {
    id: number;
    bounding_box: { x1: number; y1: number; x2: number; y2: number };
    confidence: number;
  }[];
}

export interface PersonImagesResponse {
  person_id: number;
  person_name: string | null;
  images: PersonImage[];
}

export const getPeople = async (): Promise<PersonItem[]> => {
  const response = await api.get<PersonItem[]>("/api/people");
  return response.data;
};

export const getPersonImages = async (
  personId: number,
): Promise<PersonImagesResponse> => {
  const response = await api.get<PersonImagesResponse>(
    `/api/people/${personId}/images`,
  );
  return response.data;
};

export const updatePersonName = async (
  personId: number,
  name: string,
): Promise<{ id: number; name: string; message: string }> => {
  const response = await api.patch(`/api/people/${personId}`, { name });
  return response.data;
};

export const triggerFaceClustering = async () => {
  const response = await api.post("/api/people/cluster");
  return response.data;
};

// ─── Feedback API ────────────────────────────────────────────────────────────

export interface PersonFeedback {
  id: number;
  feedback_type: string;
  source_person_id: number;
  target_person_id?: number | null;
  face_ids: number[];
  status: string;
  created_at: string;
}

export interface GeneralFeedback {
  id: number;
  feedback_type: string;
  media_id?: number | null;
  person_id?: number | null;
  rating?: number | null;
  rating_reason?: string | null;
  extra_metadata?: Record<string, unknown> | null;
  created_at: string;
}

export const submitPersonFeedbackSplit = async (
  personId: number,
  faceIds: number[],
  reason?: string,
): Promise<PersonFeedback> => {
  const response = await api.post<PersonFeedback>(
    `/api/people/${personId}/feedback/split`,
    {
      feedback_type: "split",
      face_ids: faceIds,
      user_reason: reason,
    },
  );
  return response.data;
};

export const submitPersonFeedbackMerge = async (
  personId: number,
  targetPersonId: number,
  reason?: string,
): Promise<PersonFeedback> => {
  const response = await api.post<PersonFeedback>(
    `/api/people/${personId}/feedback/merge/${targetPersonId}`,
    {
      feedback_type: "merge",
      face_ids: [],
      user_reason: reason,
    },
  );
  return response.data;
};

export const submitPersonFeedbackWrongPerson = async (
  personId: number,
  faceIds: number[],
  reason?: string,
): Promise<PersonFeedback> => {
  const response = await api.post<PersonFeedback>(
    `/api/people/${personId}/feedback/wrong-person`,
    {
      feedback_type: "wrong_person",
      face_ids: faceIds,
      user_reason: reason,
    },
  );
  return response.data;
};

export const submitPersonFeedbackCorrect = async (
  personId: number,
  faceIds?: number[],
  reason?: string,
): Promise<PersonFeedback> => {
  const response = await api.post<PersonFeedback>(
    `/api/people/${personId}/feedback/correct`,
    {
      feedback_type: "correct",
      face_ids: faceIds || [],
      user_reason: reason,
    },
  );
  return response.data;
};

export const submitSearchRating = async (
  mediaId: number,
  rating: number,
  reason?: string,
): Promise<GeneralFeedback> => {
  const response = await api.post<GeneralFeedback>(
    "/api/feedback/search-rating",
    {
      feedback_type: "search_rating",
      media_id: mediaId,
      rating,
      rating_reason: reason,
    },
  );
  return response.data;
};

export const submitCaptionRating = async (
  mediaId: number,
  rating: number,
  reason?: string,
): Promise<GeneralFeedback> => {
  const response = await api.post<GeneralFeedback>(
    "/api/feedback/caption-rating",
    {
      feedback_type: "caption_rating",
      media_id: mediaId,
      rating,
      rating_reason: reason,
    },
  );
  return response.data;
};

export const submitObjectRating = async (
  mediaId: number,
  rating: number,
  reason?: string,
): Promise<GeneralFeedback> => {
  const response = await api.post<GeneralFeedback>(
    "/api/feedback/object-rating",
    {
      feedback_type: "object_rating",
      media_id: mediaId,
      rating,
      rating_reason: reason,
    },
  );
  return response.data;
};

export const submitCaptionCorrection = async (
  mediaId: number,
  correctedCaption: string,
  reason?: string,
): Promise<GeneralFeedback> => {
  const response = await api.post<GeneralFeedback>(
    "/api/feedback/caption-correction",
    {
      feedback_type: "caption_correction",
      media_id: mediaId,
      corrected_caption: correctedCaption,
      rating_reason: reason,
    },
  );
  return response.data;
};

export const submitObjectCorrection = async (
  mediaId: number,
  correctedObjects: string[],
  reason?: string,
): Promise<GeneralFeedback> => {
  const response = await api.post<GeneralFeedback>(
    "/api/feedback/object-correction",
    {
      feedback_type: "object_correction",
      media_id: mediaId,
      corrected_objects: correctedObjects,
      rating_reason: reason,
    },
  );
  return response.data;
};

export const getFeedbackStats = async () => {
  const response = await api.get("/api/feedback/stats");
  return response.data;
};

export const getPersonFeedback = async (personId?: number) => {
  const params = personId ? { person_id: personId } : {};
  const response = await api.get("/api/people/feedback", { params });
  return response.data;
};
