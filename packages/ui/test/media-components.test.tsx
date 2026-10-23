// Behaviour and accessibility of the media manager's building blocks (handbook/DESIGN_SYSTEM.md §9):
// Switch, ProgressBar, FileDropZone, FileButton and SegmentedControl.
import { useState } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Dialog, FileButton, FileDropZone, ProgressBar, SegmentedControl, Switch } from "../src";

afterEach(cleanup);

function ControlledSwitch({ busy = false }: { busy?: boolean }) {
  const [shown, setShown] = useState(true);
  return (
    <Switch
      checked={shown}
      onChange={setShown}
      busy={busy}
      label="Show on website"
      stateText={{ on: "Shown", off: "Hidden" }}
      context="Tower A at night"
    />
  );
}

describe("Switch", () => {
  it("is a named switch that says its state in words", () => {
    render(<ControlledSwitch />);
    const toggle = screen.getByRole("switch", {
      name: "Show on website · Shown: Tower A at night",
    });
    expect(toggle.getAttribute("aria-checked")).toBe("true");
    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-checked")).toBe("false");
    expect(toggle.textContent).toContain("Show on website · Hidden");
  });

  it("ignores clicks while busy but stays focusable", () => {
    render(<ControlledSwitch busy />);
    const toggle = screen.getByRole("switch");
    expect(toggle.getAttribute("aria-disabled")).toBe("true");
    expect(toggle.getAttribute("aria-busy")).toBe("true");
    expect(toggle.hasAttribute("disabled")).toBe(false);
    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-checked")).toBe("true");
  });
});

describe("ProgressBar", () => {
  it("exposes its value to assistive technology", () => {
    render(<ProgressBar value={42.4} label="Uploading tower.jpg" valueText="1.2 of 2.9 MB" />);
    const bar = screen.getByRole("progressbar", { name: "Uploading tower.jpg" });
    expect(bar.getAttribute("aria-valuenow")).toBe("42");
    expect(bar.getAttribute("aria-valuemin")).toBe("0");
    expect(bar.getAttribute("aria-valuemax")).toBe("100");
    expect(bar.getAttribute("aria-valuetext")).toBe("1.2 of 2.9 MB");
  });

  it("clamps the value and is indeterminate without one", () => {
    const { rerender } = render(<ProgressBar value={140} label="Uploading" />);
    expect(screen.getByRole("progressbar").getAttribute("aria-valuenow")).toBe("100");
    rerender(<ProgressBar value={null} label="Preparing" />);
    const bar = screen.getByRole("progressbar", { name: "Preparing" });
    expect(bar.hasAttribute("aria-valuenow")).toBe(false);
  });
});

function pngFile(name = "tower.png") {
  return new File([new Uint8Array([0x89, 0x50, 0x4e, 0x47])], name, { type: "image/png" });
}

describe("FileDropZone", () => {
  it("is a real button described by the allowed types, backed by a file input", () => {
    const onFiles = vi.fn();
    const { container } = render(
      <FileDropZone onFiles={onFiles} accept="image/*" hint="Photos up to 10 MB" id="drop" />,
    );
    const button = screen.getByRole("button", { name: "Drag files here or browse" });
    expect(button.id).toBe("drop");
    const hint = screen.getByText("Photos up to 10 MB");
    expect(button.getAttribute("aria-describedby")).toBe(hint.id);

    const input = container.querySelector<HTMLInputElement>('input[type="file"]');
    expect(input?.accept).toBe("image/*");
    expect(input?.multiple).toBe(true);
    const click = vi.spyOn(input as HTMLInputElement, "click");
    fireEvent.click(button);
    expect(click).toHaveBeenCalledTimes(1);

    fireEvent.change(input as HTMLInputElement, { target: { files: [pngFile()] } });
    expect(onFiles).toHaveBeenCalledWith([expect.objectContaining({ name: "tower.png" })]);
  });

  it("accepts dropped files and highlights while dragging", () => {
    const onFiles = vi.fn();
    render(<FileDropZone onFiles={onFiles} hint="Any file" />);
    const button = screen.getByRole("button");
    const zone = button.closest("div")?.parentElement as HTMLElement;
    const dataTransfer = { types: ["Files"], files: [pngFile("a.png"), pngFile("b.png")] };
    fireEvent.dragEnter(zone, { dataTransfer });
    expect(screen.getByRole("button", { name: "Drop to upload" })).toBeTruthy();
    fireEvent.drop(zone, { dataTransfer });
    expect(onFiles).toHaveBeenCalledWith([
      expect.objectContaining({ name: "a.png" }),
      expect.objectContaining({ name: "b.png" }),
    ]);
    expect(screen.getByRole("button", { name: "Drag files here or browse" })).toBeTruthy();
  });

  it("ignores drops and clicks while disabled", () => {
    const onFiles = vi.fn();
    const { container } = render(<FileDropZone onFiles={onFiles} hint="Any file" disabled />);
    const button = screen.getByRole("button");
    expect(button.getAttribute("aria-disabled")).toBe("true");
    const input = container.querySelector<HTMLInputElement>('input[type="file"]');
    const click = vi.spyOn(input as HTMLInputElement, "click");
    fireEvent.click(button);
    expect(click).not.toHaveBeenCalled();
    const zone = button.closest("div")?.parentElement as HTMLElement;
    fireEvent.drop(zone, { dataTransfer: { types: ["Files"], files: [pngFile()] } });
    expect(onFiles).not.toHaveBeenCalled();
  });
});

describe("FileButton", () => {
  it("opens the chooser and passes the chosen file on", () => {
    const onFiles = vi.fn();
    const { container } = render(
      <FileButton onFiles={onFiles} accept="image/png,image/jpeg">
        Upload QR image
      </FileButton>,
    );
    const input = container.querySelector<HTMLInputElement>('input[type="file"]');
    expect(input?.multiple).toBe(false);
    const click = vi.spyOn(input as HTMLInputElement, "click");
    fireEvent.click(screen.getByRole("button", { name: "Upload QR image" }));
    expect(click).toHaveBeenCalledTimes(1);
    fireEvent.change(input as HTMLInputElement, { target: { files: [pngFile("qr.png")] } });
    expect(onFiles).toHaveBeenCalledWith([expect.objectContaining({ name: "qr.png" })]);
  });
});

function Kinds() {
  const [kind, setKind] = useState<"photo" | "video" | "document">("photo");
  return (
    <SegmentedControl
      label="Media type"
      value={kind}
      onChange={setKind}
      options={[
        { value: "photo", label: "Photos · 3" },
        { value: "video", label: "Videos · 1" },
        { value: "document", label: "Documents · 0" },
      ]}
    />
  );
}

describe("SegmentedControl", () => {
  it("is a radio group with a roving tab stop and arrow keys", () => {
    render(<Kinds />);
    expect(screen.getByRole("radiogroup", { name: "Media type" })).toBeTruthy();
    const photos = screen.getByRole("radio", { name: "Photos · 3" });
    const videos = screen.getByRole("radio", { name: "Videos · 1" });
    const documents = screen.getByRole("radio", { name: "Documents · 0" });
    expect(photos.getAttribute("aria-checked")).toBe("true");
    expect(photos.tabIndex).toBe(0);
    expect(videos.tabIndex).toBe(-1);

    fireEvent.keyDown(photos, { key: "ArrowRight" });
    expect(videos.getAttribute("aria-checked")).toBe("true");
    expect(document.activeElement).toBe(videos);
    fireEvent.keyDown(videos, { key: "End" });
    expect(documents.getAttribute("aria-checked")).toBe("true");
    fireEvent.keyDown(documents, { key: "ArrowRight" });
    expect(photos.getAttribute("aria-checked")).toBe("true");
    fireEvent.click(videos);
    expect(videos.getAttribute("aria-checked")).toBe("true");
    expect(photos.tabIndex).toBe(-1);
  });
});

function DetailsDialog({ busy = false }: { busy?: boolean }) {
  const [open, setOpen] = useState(true);
  const [saved, setSaved] = useState("");
  const [title, setTitle] = useState("Tower A");
  return (
    <>
      <p>{saved}</p>
      <Dialog
        open={open}
        title="Photo details"
        busy={busy}
        onClose={() => setOpen(false)}
        onSubmit={() => setSaved(`Saved ${title}`)}
        footer={
          <>
            <button type="button" onClick={() => setOpen(false)}>
              Cancel
            </button>
            <button type="submit">Save details</button>
          </>
        }
      >
        <label>
          Title
          <input value={title} onChange={(e) => setTitle(e.target.value)} />
        </label>
      </Dialog>
    </>
  );
}

describe("Dialog", () => {
  it("is labelled by its title, focuses the first field and submits its form", () => {
    render(<DetailsDialog />);
    const dialog = screen.getByRole("dialog", { name: "Photo details" });
    const field = screen.getByLabelText("Title");
    expect(document.activeElement).toBe(field);
    fireEvent.change(field, { target: { value: "Tower B" } });
    fireEvent.click(screen.getByRole("button", { name: "Save details" }));
    expect(screen.getByText("Saved Tower B")).toBeTruthy();
    expect(dialog.hasAttribute("open")).toBe(true);
  });

  it("closes on Escape, but not while busy", () => {
    const { unmount } = render(<DetailsDialog busy />);
    const busyDialog = screen.getByRole("dialog");
    fireEvent(busyDialog, new Event("cancel", { cancelable: true }));
    fireEvent.click(screen.getByRole("button", { name: "Save details" }));
    expect(screen.queryByText(/^Saved/)).toBeNull();
    expect(busyDialog.hasAttribute("open")).toBe(true);
    unmount();

    render(<DetailsDialog />);
    const dialog = screen.getByRole("dialog");
    fireEvent(dialog, new Event("cancel", { cancelable: true }));
    expect(dialog.hasAttribute("open")).toBe(false);
  });
});
