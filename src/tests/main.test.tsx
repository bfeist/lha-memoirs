import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { screen } from "@testing-library/dom";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Index from "@/pages/Index";

describe("Index", () => {
  it("renders without crashing", () => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <Index />
        </BrowserRouter>
      </QueryClientProvider>
    );
    // Verify the app renders with expected content
    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
  });
});
