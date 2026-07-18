import { create } from "zustand";
import type { DateRangePreset, SortOrder } from "@/lib/api";

export type GalleryFilter = "all" | "indexed" | "processing" | "failed";

export type GalleryFilterState = {
  filter: GalleryFilter;
  likedOnly: boolean;
  sortOrder: SortOrder;
  dateRange: DateRangePreset | undefined;
  dateStart: string | null;
  dateEnd: string | null;
};

type GalleryStore = GalleryFilterState & {
  setFilters: (filters: Partial<GalleryFilterState>) => void;
  resetFilters: () => void;
};

const defaultGalleryFilters: GalleryFilterState = {
  filter: "all",
  likedOnly: false,
  sortOrder: "newest",
  dateRange: undefined,
  dateStart: null,
  dateEnd: null,
};

export const galleryStore = create<GalleryStore>((set) => ({
  ...defaultGalleryFilters,
  setFilters: (filters) => {
    set((state) => {
      const nextState = {
        ...state,
        ...filters,
      };

      if (
        state.filter === nextState.filter &&
        state.likedOnly === nextState.likedOnly &&
        state.sortOrder === nextState.sortOrder &&
        state.dateRange === nextState.dateRange &&
        state.dateStart === nextState.dateStart &&
        state.dateEnd === nextState.dateEnd
      ) {
        return state;
      }

      return nextState;
    });
  },
  resetFilters: () => set(defaultGalleryFilters),
}));
