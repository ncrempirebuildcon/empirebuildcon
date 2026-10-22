"use client";
/**
 * Create a project with the minimum the API needs (name and construction status) plus an optional
 * city, then open the editor. The web address (slug) is made from the name by the API.
 *
 * New projects always start as drafts; nothing here can publish (ARCHITECTURE.md §11).
 */
import Link from "next/link";
import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Alert, Button, Select, TextField } from "@empire/ui";
import { api, call } from "@/lib/api";
import { PROJECT_STATUS, keyOf, optionsOf, type ProjectStatus } from "@/lib/labels";
import { fieldErrors, problemMessage, type FieldErrors } from "@/lib/problems";
import { CATALOGUE_PATH, PROJECTS_PATH, projectPath } from "@/lib/routes";
import { useLoad } from "@/components/admin/useLoad";
import { useAdminSession } from "../../session-context";
import { DEFAULT_RERA_AUTHORITY, DEFAULT_STATE } from "../[id]/projectForm";

export function NewProjectForm() {
  const router = useRouter();
  const { can } = useAdminSession();
  const [name, setName] = useState("");
  const [status, setStatus] = useState<ProjectStatus>("ongoing");
  const [cityId, setCityId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errors, setErrors] = useState<FieldErrors>({});
  const cities = useLoad("cities", () =>
    call(api.GET("/api/v1/admin/cities", { params: { query: { per_page: 100 } } })),
  );

  if (!can("projects.write")) {
    return (
      <Alert tone="info" title="Your role can view projects but not add them.">
        Ask an admin or a content editor to add the project.{" "}
        <Link href={PROJECTS_PATH} className="font-bold underline">
          Back to projects
        </Link>
      </Alert>
    );
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setError(null);
    if (!name.trim()) {
      setErrors({ name: "Enter the project's name." });
      return;
    }
    setErrors({});
    setBusy(true);
    const city = cities.data?.items.find((c) => c.id === cityId);
    try {
      const project = await call(
        api.POST("/api/v1/admin/projects", {
          // The API's defaults for a new draft, sent explicitly because the generated type
          // requires every field that has a default.
          body: {
            name: name.trim(),
            status,
            sales_status: "available",
            project_type: "residential",
            rera_authority: DEFAULT_RERA_AUTHORITY,
            is_featured: false,
            brochure_gated: false,
            location: { state: city?.state ?? DEFAULT_STATE, city_id: cityId || null },
          },
        }),
      );
      router.push(projectPath(project.id));
    } catch (err) {
      setBusy(false);
      setErrors(fieldErrors(err));
      setError(problemMessage(err, "Couldn't create the project."));
    }
  }

  const cityOptions = (cities.data?.items ?? []).map((city) => ({
    value: city.id,
    label: city.state ? `${city.name}, ${city.state}` : city.name,
  }));

  return (
    <section
      aria-labelledby="new-project-title"
      className="flex max-w-2xl flex-col gap-5 rounded-card border border-line bg-noir-800 p-5 md:p-6"
    >
      <div>
        <h2 id="new-project-title" className="text-[17px] font-bold">
          Start a project
        </h2>
        <p className="mt-1 text-small text-muted">
          It is saved as a draft. You add RERA details, prices, configurations and the rest on the
          next screen; nothing appears on the website until it is published.
        </p>
      </div>
      <form noValidate onSubmit={onSubmit} className="flex flex-col gap-5">
        {error ? <Alert tone="error">{error}</Alert> : null}
        <TextField
          label="Project name"
          required
          maxLength={120}
          autoComplete="off"
          value={name}
          onChange={(event) => setName(event.target.value)}
          error={errors.name ?? errors.slug}
          hint="The web address is made from the name; you can change it later."
        />
        <Select
          label="Construction status"
          value={status}
          options={optionsOf(PROJECT_STATUS)}
          onChange={(event) => setStatus(keyOf(PROJECT_STATUS, event.target.value, "ongoing"))}
          error={errors.status}
        />
        <Select
          label="City (optional)"
          value={cityId}
          placeholder={cities.loading ? "Loading cities…" : "Choose later"}
          options={cityOptions}
          onChange={(event) => setCityId(event.target.value)}
          error={errors["location.city_id"]}
          hint={
            <>
              Missing a city? Add it under{" "}
              <Link href={CATALOGUE_PATH} className="underline">
                Catalogue
              </Link>
              .
            </>
          }
        />
        <div className="flex flex-wrap gap-3">
          <Button type="submit" loading={busy}>
            Create draft
          </Button>
          <Link href={PROJECTS_PATH} className="inline-flex min-h-11 items-center px-2 font-bold">
            Cancel
          </Link>
        </div>
      </form>
    </section>
  );
}
