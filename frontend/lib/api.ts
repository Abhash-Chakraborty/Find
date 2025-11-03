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
export interface MediaItem {
  id: number;
  filename: string;
  minio_key: string;
  status: "pending" | "processing" | "indexed" | "failed";
  created_at: string;
  processed_at?: string | null;
  width?: number | null;
  height?: number | null;
  file_size?: number | null;
  cluster_id?: number | null;
  url?: string | null;
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
  limit: number;
}

export interface ClusterSample {
  id: number;
  filename: string;
  url?: string | null;
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
    caption?: string;
  }>;
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
}

export interface JobStatus {
  job_id: string;
  status: "queued" | "started" | "finished" | "failed";
  created_at?: string | null;
  started_at?: string | null;
  ended_at?: string | null;
  result?: unknown;
  error?: string;
}

// API Functions
export const uploadImages = async (
  files: FileList | File[]
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
  zipFile: File
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
    }
  );

  return response.data;
};

export const getJobStatus = async (jobId: string): Promise<JobStatus> => {
  const response = await api.get<JobStatus>(`/api/status/${jobId}`);
  return response.data;
};

export const getGallery = async (
  params: {
    page?: number;
    limit?: number;
    status?: string;
    liked?: boolean;
  } = {}
): Promise<GalleryResponse> => {
  const response = await api.get<GalleryResponse>("/api/gallery", { params });
  return response.data;
};

export const getImageDetail = async (mediaId: number): Promise<MediaDetail> => {
  const response = await api.get<MediaDetail>(`/api/image/${mediaId}`);
  return response.data;
};

export const toggleLike = async (
  mediaId: number
): Promise<{ id: number; liked: boolean }> => {
  const response = await api.post<{ id: number; liked: boolean }>(
    `/api/image/${mediaId}/like`
  );
  return response.data;
};

export const deleteImage = async (
  mediaId: number
): Promise<{ id: number; message: string }> => {
  const response = await api.delete<{ id: number; message: string }>(
    `/api/image/${mediaId}`
  );
  return response.data;
};

export const searchImages = async (params: {
  query: string;
  limit?: number;
}): Promise<SearchResponse> => {
  const response = await api.get<SearchResponse>("/api/search", {
    params: { q: params.query, limit: params.limit || 20 },
  });
  return response.data;
};

export const getClusters = async (): Promise<ClustersResponse> => {
  const response = await api.get<ClustersResponse>("/api/clusters");
  return response.data;
};

export const getClusterDetail = async (
  clusterId: number
): Promise<ClusterDetail> => {
  const response = await api.get<ClusterDetail>(`/api/cluster/${clusterId}`);
  return response.data;
};

export const triggerClustering = async (): Promise<{
  message: string;
  job_id: string;
}> => {
  const response = await api.post<{ message: string; job_id: string }>(
    "/api/cluster/run"
  );
  return response.data;
};
