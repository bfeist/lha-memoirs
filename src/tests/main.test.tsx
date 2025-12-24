import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import Index from "@/pages/Index";

describe("Index", () => {
  it("renders without crashing", () => {
    render(
      <BrowserRouter>
        <Index />
      </BrowserRouter>
    );
    // Verify the app renders with expected content
    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
  });
});
