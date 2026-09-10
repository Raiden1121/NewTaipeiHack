import { create } from "zustand";

interface SelectedDistrictState {
  selectedDistrictId: string | null;
  selectDistrict: (districtId: string) => void;
  clearSelection: () => void;
}

export const useSelectedDistrict = create<SelectedDistrictState>((set) => ({
  selectedDistrictId: null,
  selectDistrict: (districtId) => set({ selectedDistrictId: districtId }),
  clearSelection: () => set({ selectedDistrictId: null }),
}));
