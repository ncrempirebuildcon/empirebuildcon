import { describe, expect, it } from "vitest";
import { cloudinaryLoader } from "../src/lib/cloudinary-loader";

describe("cloudinaryLoader", () => {
  it("leaves non-Cloudinary URLs completely untouched", () => {
    const local = "/media/sample-hero.jpg";
    expect(cloudinaryLoader({ src: local, width: 800 })).toBe(local);

    const external = "https://example.com/photo.png";
    expect(cloudinaryLoader({ src: external, width: 800 })).toBe(external);
  });

  it("rejects hostnames that only contain res.cloudinary.com as a substring (S12)", () => {
    const spoofed = "https://res.cloudinary.com.attacker.com/demo/image/upload/sample.jpg";
    expect(cloudinaryLoader({ src: spoofed, width: 800 })).toBe(spoofed);
  });

  it("injects c_limit, f_auto, q_auto, and requested width into upload URLs", () => {
    const src = "https://res.cloudinary.com/demo/image/upload/v1234567/sample.jpg";
    const result = cloudinaryLoader({ src, width: 1200 });
    expect(result).toBe(
      "https://res.cloudinary.com/demo/image/upload/c_limit,f_auto,q_auto,w_1200/v1234567/sample.jpg",
    );
  });

  it("replaces existing delivery transformations while preserving version and id", () => {
    const src =
      "https://res.cloudinary.com/demo/image/upload/c_limit,f_auto,q_auto,w_2560/v1234567/sample.jpg";
    const result = cloudinaryLoader({ src, width: 640 });
    expect(result).toBe(
      "https://res.cloudinary.com/demo/image/upload/c_limit,f_auto,q_auto,w_640/v1234567/sample.jpg",
    );
  });

  it("does not drop folder segment when URL has no version prefix (S12)", () => {
    const src = "https://res.cloudinary.com/demo/image/upload/projects/exterior/hero.jpg";
    const result = cloudinaryLoader({ src, width: 800 });
    expect(result).toBe(
      "https://res.cloudinary.com/demo/image/upload/c_limit,f_auto,q_auto,w_800/projects/exterior/hero.jpg",
    );
  });

  it("supports custom quality when specified", () => {
    const src = "https://res.cloudinary.com/demo/image/upload/v1234567/sample.jpg";
    const result = cloudinaryLoader({ src, width: 800, quality: 75 });
    expect(result).toBe(
      "https://res.cloudinary.com/demo/image/upload/c_limit,f_auto,q_75,w_800/v1234567/sample.jpg",
    );
  });

  it("returns empty string when src is empty", () => {
    expect(cloudinaryLoader({ src: "", width: 800 })).toBe("");
  });
});
