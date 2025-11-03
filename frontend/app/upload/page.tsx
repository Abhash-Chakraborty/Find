"use client";

import { useCallback, useMemo, useState } from "react";
import { useDropzone } from "react-dropzone";
import { useMutation } from "@tanstack/react-query";
import { uploadImages, uploadImagesBulk, type UploadResult } from "@/lib/api";
import { toast } from "sonner";
import {
  Upload,
  CheckCircle,
  XCircle,
  Loader2,
  Image as ImageIcon,
  Package,
} from "lucide-react";

type UploadMode = "single" | "bulk";

export default function UploadPage() {
  const [uploadedFiles, setUploadedFiles] = useState<UploadResult[]>([]);
  const [mode, setMode] = useState<UploadMode>("single");
  const parsedBulkLimit = Number(
    process.env.NEXT_PUBLIC_MAX_BULK_FILES ?? "200"
  );
  const maxBulkFiles =
    Number.isFinite(parsedBulkLimit) && parsedBulkLimit > 0
      ? Math.floor(parsedBulkLimit)
      : 200;

  const uploadMutation = useMutation({
    mutationFn: uploadImages,
    onSuccess: (data) => {
      setUploadedFiles((prev) => [...data.results, ...prev]);
      toast.success(
        `Processed ${data.total} file${data.total === 1 ? "" : "s"}`
      );
    },
    onError: () => {
      toast.error("Upload failed");
    },
  });

  const bulkUploadMutation = useMutation({
    mutationFn: uploadImagesBulk,
    onSuccess: (data) => {
      setUploadedFiles((prev) => [...data.results, ...prev]);
      const uploadedCount = data.results.filter(
        (item) => item.status === "uploaded"
      ).length;
      toast.success(
        `Archive processed (${uploadedCount} new upload${
          uploadedCount === 1 ? "" : "s"
        })`
      );
    },
    onError: () => {
      toast.error("Bulk upload failed");
    },
  });

  const isUploading = uploadMutation.isPending || bulkUploadMutation.isPending;

  const onDrop = useCallback(
    (acceptedFiles: File[]) => {
      if (acceptedFiles.length === 0) {
        toast.error("No valid images selected");
        return;
      }

      const fileList = Object.assign(acceptedFiles, {
        item: (index: number) => acceptedFiles[index] || null,
      }) as unknown as FileList;

      uploadMutation.mutate(fileList);
    },
    [uploadMutation]
  );

  const onBulkDrop = useCallback(
    (acceptedFiles: File[]) => {
      if (acceptedFiles.length === 0) {
        toast.error("No archive selected");
        return;
      }

      const [archive] = acceptedFiles;
      if (!archive) {
        toast.error("No archive selected");
        return;
      }

      bulkUploadMutation.mutate(archive);
    },
    [bulkUploadMutation]
  );

  const {
    getRootProps: getSingleRootProps,
    getInputProps: getSingleInputProps,
    isDragActive: isSingleDragActive,
    fileRejections: singleRejections,
  } = useDropzone({
    onDrop,
    accept: {
      "image/jpeg": [".jpg", ".jpeg"],
      "image/png": [".png"],
      "image/webp": [".webp"],
      "image/gif": [".gif"],
    },
    maxSize: 50 * 1024 * 1024,
    multiple: true,
    disabled: mode !== "single" || isUploading,
  });

  const {
    getRootProps: getBulkRootProps,
    getInputProps: getBulkInputProps,
    isDragActive: isBulkDragActive,
    fileRejections: bulkRejections,
  } = useDropzone({
    onDrop: onBulkDrop,
    accept: {
      "application/zip": [".zip"],
      "application/x-zip-compressed": [".zip"],
    },
    maxFiles: 1,
    multiple: false,
    disabled: mode !== "bulk" || isUploading,
  });

  const activeRootProps =
    mode === "single" ? getSingleRootProps : getBulkRootProps;
  const activeInputProps =
    mode === "single" ? getSingleInputProps : getBulkInputProps;
  const isDragActive =
    mode === "single" ? isSingleDragActive : isBulkDragActive;
  const fileRejections = mode === "single" ? singleRejections : bulkRejections;
  const helperText = useMemo(() => {
    if (mode === "single") {
      return "JPEG, PNG, WebP, GIF • Max 50MB each";
    }
    return `Upload a ZIP archive up to ${maxBulkFiles} images`;
  }, [mode, maxBulkFiles]);

  return (
    <div className="min-h-screen bg-white">
      <div className="max-w-4xl mx-auto px-6 py-12">
        <div className="mb-12">
          <h1 className="text-4xl font-light mb-3 text-black">Upload</h1>
          <p className="text-gray-500 text-sm">Add images to analyze with AI</p>
        </div>

        <div className="flex gap-2 mb-6">
          <button
            type="button"
            onClick={() => setMode("single")}
            className={`px-4 py-2 text-sm font-medium border transition-colors ${
              mode === "single"
                ? "border-black text-black"
                : "border-gray-200 text-gray-500 hover:text-black"
            }`}
          >
            Individual files
          </button>
          <button
            type="button"
            onClick={() => setMode("bulk")}
            className={`px-4 py-2 text-sm font-medium border transition-colors ${
              mode === "bulk"
                ? "border-black text-black"
                : "border-gray-200 text-gray-500 hover:text-black"
            }`}
          >
            ZIP archive
          </button>
        </div>

        <div
          {...activeRootProps()}
          className={`
            border-2 border-dashed rounded-sm p-16 text-center cursor-pointer transition-all
            ${
              isDragActive
                ? "border-black bg-gray-50"
                : "border-gray-200 hover:border-gray-300"
            }
            ${isUploading ? "opacity-50 pointer-events-none" : ""}
          `}
        >
          <input {...activeInputProps()} />
          {mode === "single" ? (
            <Upload className="w-12 h-12 mx-auto mb-4 text-gray-300" />
          ) : (
            <Package className="w-12 h-12 mx-auto mb-4 text-gray-300" />
          )}

          {isDragActive ? (
            <p className="text-base font-medium text-black">Drop images here</p>
          ) : (
            <>
              <p className="text-base font-medium mb-2 text-black">
                {mode === "single"
                  ? "Drop images or click to browse"
                  : "Drop a ZIP archive or click to browse"}
              </p>
              <p className="text-sm text-gray-400">{helperText}</p>
            </>
          )}
        </div>

        {fileRejections.length > 0 && (
          <div className="mt-6 p-4 bg-red-50 border border-red-100 rounded-sm">
            <p className="text-sm font-medium text-red-900 mb-2">
              Some files were rejected:
            </p>
            <ul className="text-sm text-red-700 space-y-1">
              {fileRejections.map(({ file, errors }) => (
                <li key={file.name}>
                  {file.name}: {errors[0]?.message}
                </li>
              ))}
            </ul>
          </div>
        )}

        {isUploading && (
          <div className="mt-6 flex items-center gap-3 text-gray-600">
            <Loader2 className="w-5 h-5 animate-spin" />
            <span className="text-sm">Uploading...</span>
          </div>
        )}

        {uploadedFiles.length > 0 && !isUploading && (
          <div className="mt-8 space-y-3">
            {uploadedFiles.map((result, idx) => (
              <div
                key={idx}
                className="flex items-center justify-between p-4 border border-gray-100 rounded-sm"
              >
                <div className="flex items-center gap-3">
                  {result.status === "uploaded" && (
                    <CheckCircle className="w-5 h-5 text-green-600" />
                  )}
                  {result.status === "duplicate" && (
                    <ImageIcon className="w-5 h-5 text-yellow-600" />
                  )}
                  {result.status === "failed" && (
                    <XCircle className="w-5 h-5 text-red-600" />
                  )}

                  <div>
                    <p className="text-sm font-medium text-black">
                      {result.filename}
                    </p>
                    {result.status === "uploaded" && (
                      <p className="text-xs text-gray-500">Processing...</p>
                    )}
                    {result.status === "duplicate" && (
                      <p className="text-xs text-gray-500">Already exists</p>
                    )}
                    {result.status === "failed" && (
                      <p className="text-xs text-red-600">
                        {result.error || "Failed"}
                      </p>
                    )}
                  </div>
                </div>

                <span
                  className={`
                  px-3 py-1 text-xs font-medium rounded-full
                  ${
                    result.status === "uploaded"
                      ? "bg-green-100 text-green-700"
                      : ""
                  }
                  ${
                    result.status === "duplicate"
                      ? "bg-yellow-100 text-yellow-700"
                      : ""
                  }
                  ${result.status === "failed" ? "bg-red-100 text-red-700" : ""}
                `}
                >
                  {result.status}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
