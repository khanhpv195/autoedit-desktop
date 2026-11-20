import { render, screen } from "@testing-library/react";
import App from "./App";

test("hiện tên app", () => {
  render(<App />);
  expect(screen.getByText("AutoEdit")).toBeInTheDocument();
});
