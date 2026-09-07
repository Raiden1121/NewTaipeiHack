import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Button } from "./button";

describe("Button", () => {
  it("applies the destructive variant class when requested", () => {
    render(<Button variant="destructive">重新載入</Button>);
    expect(screen.getByRole("button", { name: "重新載入" })).toHaveClass(
      "bg-risk-high",
    );
  });
});
