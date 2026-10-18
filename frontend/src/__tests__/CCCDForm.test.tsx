import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import CCCDForm from "@/components/form/CCCDForm";
import type { CCCDData } from "@/lib/schemas";

const VALID_DATA: CCCDData = {
  id_number: "001202000123",
  full_name: "NGUYEN VAN A",
  dob: "01/01/2002",
  gender: "Nam",
  nationality: "Viet Nam",
  origin: "Quan 1, TP HCM",
  residence: "123 Le Loi, Quan 1, TP HCM",
  expiry_date: "01/01/2030",
};

describe("CCCDForm", () => {
  it("submits edited form data", async () => {
    const onExport = vi.fn();
    render(<CCCDForm initialData={VALID_DATA} onExport={onExport} />);

    fireEvent.change(screen.getByLabelText("Họ và tên"), {
      target: { value: "TRAN THI B" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Xuất file Excel" }));

    await waitFor(() => {
      expect(onExport).toHaveBeenCalledWith(
        expect.objectContaining({ full_name: "TRAN THI B" }),
      );
    });
  });

  it("shows realtime validation and blocks submit when invalid", async () => {
    const onExport = vi.fn();
    render(<CCCDForm initialData={VALID_DATA} onExport={onExport} />);

    fireEvent.change(screen.getByLabelText("Số CCCD"), {
      target: { value: "123" },
    });

    expect(
      screen.getByText("Số CCCD phải gồm đúng 12 chữ số"),
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "Kiểm tra lại thông tin" }),
    );

    await waitFor(() => {
      expect(onExport).not.toHaveBeenCalled();
    });
  });

  it("auto-focuses the lowest confidence field", async () => {
    render(
      <CCCDForm
        initialData={VALID_DATA}
        confidences={{
          id_number: 0.41,
          full_name: 0.96,
          dob: 0.95,
        }}
        onExport={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(screen.getByLabelText("Số CCCD")).toHaveFocus();
    });
  });

  it("requires unread (confidence 0) fields to be reviewed before export", () => {
    const onExport = vi.fn();
    render(
      <CCCDForm
        initialData={{ ...VALID_DATA, dob: "01/01/2000" }}
        confidences={{ dob: 0, full_name: 0.95 }}
        onExport={onExport}
      />,
    );
    const dob = screen.getByLabelText("Ngày sinh");
    // Ô được auto-focus: rời ô đó không tính là đã kiểm tra.
    fireEvent.blur(dob);
    expect(screen.getByRole("button", { name: "Kiểm tra lại thông tin" })).toBeDisabled();

    fireEvent.mouseDown(dob);
    fireEvent.focus(dob);
    fireEvent.blur(dob);
    fireEvent.click(screen.getByRole("button", { name: "Xuất file Excel" }));
    expect(onExport).toHaveBeenCalledTimes(1);
  });

  it("does not steal focus when confidences are refreshed by polling", () => {
    const props = { initialData: VALID_DATA, onExport: vi.fn() };
    const { rerender } = render(<CCCDForm {...props} confidences={{ id_number: 0.4 }} />);
    const name = screen.getByLabelText("Họ và tên");
    name.focus();
    rerender(<CCCDForm {...props} confidences={{ id_number: 0.4 }} />);
    expect(name).toHaveFocus();
  });
});
