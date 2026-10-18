import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { toast } from "sonner";

import ImageUpload from "@/components/upload/ImageUpload";
import * as image from "@/lib/image";

vi.mock("sonner", () => ({ toast: { warning: vi.fn() } }));

function dropFiles(files: File[]) {
  const zone = screen.getByText(/Kéo thả hoặc chọn/).parentElement as HTMLElement;
  fireEvent.drop(zone, { dataTransfer: { files } });
}

describe("ImageUpload", () => {
  beforeEach(() => {
    vi.spyOn(image, "prepareImageForUpload").mockImplementation(async (f) => f);
    globalThis.URL.createObjectURL = vi.fn(() => "blob:preview");
    globalThis.URL.revokeObjectURL = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("accepts images, HEIC and PDF but skips other files", async () => {
    const onImagesSelect = vi.fn();
    render(<ImageUpload onImagesSelect={onImagesSelect} isLoading={false} />);

    const jpg = new File(["a"], "front.jpg", { type: "image/jpeg" });
    const heic = new File(["b"], "back.HEIC", { type: "" });
    const pdf = new File(["c"], "hoso.pdf", { type: "application/pdf" });
    const zip = new File(["d"], "cards.zip", { type: "application/zip" });
    dropFiles([jpg, heic, pdf, zip]);

    await waitFor(() => expect(onImagesSelect).toHaveBeenCalledWith([jpg, heic, pdf]));
    expect(toast.warning).toHaveBeenCalledWith("Đã bỏ qua tệp không hợp lệ", expect.anything());
    expect(screen.getByText("hoso.pdf")).toBeInTheDocument();
  });

  it("shows a preparing state while images are being compressed", async () => {
    let release!: () => void;
    vi.spyOn(image, "prepareImageForUpload").mockImplementation(
      (f) => new Promise((resolve) => (release = () => resolve(f))),
    );
    const onImagesSelect = vi.fn();
    render(<ImageUpload onImagesSelect={onImagesSelect} isLoading={false} />);

    dropFiles([new File(["a"], "a.png", { type: "image/png" })]);

    expect(await screen.findByText("Đang chuẩn bị ảnh...")).toBeInTheDocument();
    expect(onImagesSelect).not.toHaveBeenCalled();

    release();
    await waitFor(() => expect(screen.getByText(/Đã chọn 1 ảnh/)).toBeInTheDocument());
    expect(onImagesSelect).toHaveBeenCalledTimes(1);
  });

  it("drops the selection if the component is reset while compressing", async () => {
    let release!: () => void;
    vi.spyOn(image, "prepareImageForUpload").mockImplementation(
      (f) => new Promise((resolve) => (release = () => resolve(f))),
    );
    const onImagesSelect = vi.fn();
    const { unmount } = render(
      <ImageUpload onImagesSelect={onImagesSelect} isLoading={false} />,
    );

    dropFiles([new File(["a"], "a.png", { type: "image/png" })]);
    await screen.findByText("Đang chuẩn bị ảnh...");
    unmount();
    release();
    await new Promise((r) => setTimeout(r, 0));

    expect(onImagesSelect).not.toHaveBeenCalled();
  });
});
