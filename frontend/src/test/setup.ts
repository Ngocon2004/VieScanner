import "@testing-library/jest-dom/vitest";

if (!global.URL.createObjectURL) {
  global.URL.createObjectURL = () => "blob:mock-url";
}

if (!global.URL.revokeObjectURL) {
  global.URL.revokeObjectURL = () => {};
}
