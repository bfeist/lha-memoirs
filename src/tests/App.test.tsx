import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import App from "@/App";

describe("App", () => {
  it("renders without crashing", () => {
    render(<App />);
    // Verify the app renders with expected content
    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
  });
});
