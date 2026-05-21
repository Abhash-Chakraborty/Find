"use client";

import { Suspense } from "react";
import { VaultGallery } from "@/components/vault/VaultGallery";

export default function VaultPage() {
  return (
    <Suspense fallback={null}>
      <VaultGallery />
    </Suspense>
  );
}
