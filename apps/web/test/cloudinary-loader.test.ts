import { describe, expect, it } from "vitest";
import { cloudinaryLoader } from "../src/lib/cloudinary-loader";

describe("cloudinaryLoader", () => {
  it("injects f_auto,q_auto,w_<width> into basic Cloudinary URL", () => {
    const src = "https://res.cloudinary.com/empire/image/upload/v1234567/sample.jpg";
    const result = cloudinaryLoader({ src, width: 800 });
    expect(result).toBe(
      "https://res.cloudinary.com/empire/image/upload/f_auto,q_auto,w_800/v1234567/sample.jpg",
    );
  });

  it("replaces existing delivery transformations with requested width", () => {
    const src =
      "https://res.cloudinary.com/empire/image/upload/c_limit,f_auto,h_2560,q_auto,w_2560/v1234567/sample.jpg";
    const result = cloudinaryLoader({ src, width: 1200 });
    expect(result).toBe(
      "https://res.cloudinary.com/empire/image/upload/f_auto,q_auto,w_1200/v1234567/sample.jpg",
    );
  });

  it("supports explicit quality argument", () => {
    const src = "https://res.cloudinary.com/empire/image/upload/v1/sample.jpg";
    const result = cloudinaryLoader({ src, width: 640, quality: 75 });
    expect(result).toBe(
      "https://res.cloudinary.com/empire/image/upload/f_auto,q_75,w_640/v1/sample.jpg",
    );
  });

  it("leaves fake media store URLs unmodified", () => {
    const src = "http://localhost:8000/media/fake-uploads/sample.jpg";
    const result = cloudinaryLoader({ src, width: 800 });
    expect(result).toBe(src);
  });

  it("leaves local relative paths unmodified", () => {
    const src = "/brand/logo-stacked-noir.svg";
    const result = cloudinaryLoader({ src, width: 320 });
    expect(result).toBe(src);
  });

  it("leaves non-image Cloudinary resources (e.g. raw) unmodified", () => {
    const src = "https://res.cloudinary.com/empire/raw/upload/v1/sample.pdf";
    const result = cloudinaryLoader({ src, width: 800 });
    expect(result).toBe(src);
  });
});
