import { describe, expect, it, beforeEach } from "vitest";
import { useSelectedDistrict } from "./useSelectedDistrict";

describe("useSelectedDistrict", () => {
  beforeEach(() => {
    useSelectedDistrict.setState({ selectedDistrictId: null });
  });

  it("starts with no district selected", () => {
    expect(useSelectedDistrict.getState().selectedDistrictId).toBeNull();
  });

  it("selectDistrict sets the selected district id", () => {
    useSelectedDistrict.getState().selectDistrict("65000010");
    expect(useSelectedDistrict.getState().selectedDistrictId).toBe(
      "65000010",
    );
  });

  it("clearSelection resets the selected district id to null", () => {
    useSelectedDistrict.getState().selectDistrict("65000010");
    useSelectedDistrict.getState().clearSelection();
    expect(useSelectedDistrict.getState().selectedDistrictId).toBeNull();
  });
});
