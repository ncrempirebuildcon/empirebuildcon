"use client";
/**
 * Location tab (board NoirCmsProject, "Location"): city and locality, address, state and PIN,
 * the map pin, and the location advantages list.
 *
 * How the pin is set (ARCHITECTURE §13):
 *   1. Paste a Google Maps link, a maps.app.goo.gl short link or a full plus code and press
 *      "Get pin". The API works out the coordinates (short links are followed on the server only).
 *   2. Or type the latitude and longitude. "Open in Google Maps" checks the pin either way.
 * TODO(phase-5): a draggable Leaflet map here, once the map component is built for the public
 * site (DESIGN_SYSTEM §8 "Map").
 *
 * The address fields save with the editor's "Save draft" button; location advantages save as
 * you go, like the other lists.
 */
import { useState } from "react";
import Link from "next/link";
import { Alert, Button, NumberField, Select, TextField, Textarea } from "@empire/ui";
import { api, call, type Schema } from "@/lib/api";
import { problemMessage } from "@/lib/problems";
import { CATALOGUE_PATH } from "@/lib/routes";
import { Panel } from "@/components/admin/states";
import { useLoad } from "@/components/admin/useLoad";
import { AdvantagesSection } from "./AdvantagesSection";
import type { FormTabProps } from "./DetailsTab";
import type { ProjectForm } from "./projectForm";
import type { ChildTabProps } from "./editorTypes";

type City = Schema<"City">;

/** Google Maps search link for a pin, used to check it by eye. */
export const mapsSearchUrl = (lat: number, lng: number) =>
  `https://www.google.com/maps/search/?api=1&query=${lat},${lng}`;

export function LocationTab(props: FormTabProps & ChildTabProps) {
  const { form, setForm, errors, canWrite } = props;
  const cities = useLoad("cities", () =>
    call(api.GET("/api/v1/admin/cities", { params: { query: { per_page: 100 } } })),
  );
  const localities = useLoad(`localities:${form.city_id}`, () =>
    form.city_id
      ? call(
          api.GET("/api/v1/admin/localities", {
            params: { query: { city_id: form.city_id, per_page: 100 } },
          }),
        )
      : Promise.resolve({ items: [], meta: { page: 1, per_page: 100, total: 0, pages: 0 } }),
  );
  const cityList: City[] = cities.data?.items ?? [];
  const localityOptions = (localities.data?.items ?? []).map((l) => ({
    value: l.id,
    label: l.name,
  }));

  function chooseCity(cityId: string) {
    const previous = cityList.find((c) => c.id === form.city_id);
    const next = cityList.find((c) => c.id === cityId);
    // Keep a hand-typed state; follow the city's state when the field still shows the old one.
    const followState = !form.state.trim() || form.state === previous?.state;
    setForm({
      city_id: cityId,
      locality_id: "",
      ...(next?.state && followState ? { state: next.state } : {}),
    });
  }

  return (
    <div className="flex flex-col gap-5">
      <fieldset disabled={!canWrite} className="flex min-w-0 flex-col gap-5">
        <legend className="sr-only">Address and map pin</legend>
        <Panel
          id="address"
          title="Address"
          description={
            <>
              Cities and localities come from the{" "}
              <Link href={CATALOGUE_PATH} className="underline">
                Catalogue
              </Link>
              .
            </>
          }
        >
          <div className="grid gap-x-5 gap-y-4 md:grid-cols-2">
            <Select
              label="City"
              value={form.city_id}
              placeholder={cities.loading && !cities.data ? "Loading cities…" : "Choose a city"}
              options={cityList.map((c) => ({ value: c.id, label: c.name }))}
              onChange={(e) => chooseCity(e.target.value)}
              error={errors["location.city_id"]}
            />
            <Select
              label="Locality"
              value={form.locality_id}
              placeholder={form.city_id ? "Choose a locality" : "Choose a city first"}
              options={localityOptions}
              disabled={!form.city_id}
              onChange={(e) => setForm({ locality_id: e.target.value })}
              error={errors["location.locality_id"]}
              hint={
                form.city_id && localities.data && localityOptions.length === 0
                  ? "This city has no localities yet. Add them under Catalogue."
                  : undefined
              }
            />
            <Textarea
              label="Address"
              rows={2}
              maxLength={300}
              value={form.address_line}
              placeholder="[Plot no.], [Sector], [Locality]"
              onChange={(e) => setForm({ address_line: e.target.value })}
              error={errors["location.address_line"]}
              className="md:col-span-2"
            />
            <TextField
              label="State"
              maxLength={60}
              value={form.state}
              onChange={(e) => setForm({ state: e.target.value })}
              error={errors["location.state"]}
            />
            <TextField
              label="PIN code"
              inputMode="numeric"
              maxLength={6}
              value={form.pincode}
              placeholder="[PIN code]"
              onChange={(e) => setForm({ pincode: e.target.value.replace(/\D/g, "") })}
              error={errors["location.pincode"]}
            />
          </div>
        </Panel>
        <MapPinPanel {...props} />
      </fieldset>
      <AdvantagesSection
        project={props.project}
        canWrite={canWrite}
        onChanged={props.onChanged}
        reportDirty={props.reportDirty}
      />
    </div>
  );
}

/** Typing coordinates by hand: the pin no longer comes from the pasted link or code. */
const MANUAL_PIN = { pin_source: "manual", google_maps_url: "", plus_code: "" } as const;

/**
 * The link or plus code the pin was taken from, as it will be saved, with a way to clear it.
 * Shown as text, not a link: it is only a record of where the pin came from.
 */
function PinReference({ form, setForm, canWrite }: Omit<FormTabProps, "errors">) {
  if (!form.google_maps_url && !form.plus_code) return null;
  const afterClear = (patch: Partial<ProjectForm>) =>
    setForm({ ...patch, pin_source: form.lat !== null && form.lng !== null ? "manual" : "" });
  const rows: Array<{ key: string; term: string; value: string; clear: Partial<ProjectForm> }> = [
    {
      key: "link",
      term: "Google Maps link",
      value: form.google_maps_url,
      clear: { google_maps_url: "" },
    },
    { key: "code", term: "Plus code", value: form.plus_code, clear: { plus_code: "" } },
  ];
  return (
    <dl className="flex flex-col gap-2 rounded-tile border border-line bg-noir-900 px-3.5 py-3 text-caption">
      {rows.map((row) =>
        row.value ? (
          <div key={row.key} className="flex flex-col gap-1">
            <dt className="font-semibold text-ivory">{row.term}</dt>
            <dd className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <span className="min-w-0 flex-[1_1_200px] text-muted [overflow-wrap:anywhere]">
                {row.value}
              </span>
              {canWrite ? (
                <Button
                  variant="secondary"
                  aria-label={`Clear ${row.term}`}
                  onClick={() => afterClear(row.clear)}
                >
                  Clear
                </Button>
              ) : null}
            </dd>
          </div>
        ) : null,
      )}
    </dl>
  );
}

function MapPinPanel({ form, setForm, errors, canWrite }: FormTabProps) {
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ tone: "success" | "error"; text: string } | null>(null);

  async function getPin() {
    const value = input.trim();
    if (!value || busy) {
      if (!value)
        setResult({ tone: "error", text: "Paste a Google Maps link or a plus code first." });
      return;
    }
    setBusy(true);
    setResult(null);
    try {
      const pin = await call(api.POST("/api/v1/admin/maps/resolve", { body: { input: value } }));
      const fromPlusCode = pin.source === "plus_code";
      // WHY: keep only what the API normalised. A plus code pasted with a place name
      // ("7JWV8XX8+XX Noida") is stored as the bare code; the link is kept only for a link.
      setForm({
        lat: pin.lat,
        lng: pin.lng,
        pin_source: fromPlusCode ? "plus_code" : "url",
        google_maps_url: fromPlusCode ? "" : (pin.resolved_url ?? value),
        plus_code: pin.plus_code ?? "",
      });
      setResult({
        tone: "success",
        text: `Pin set to ${pin.lat}, ${pin.lng}. Check it with “Open in Google Maps”, then save.`,
      });
    } catch (err) {
      setResult({
        tone: "error",
        text: problemMessage(
          err,
          "Couldn't read a pin from that. Paste the full Google Maps link.",
        ),
      });
    } finally {
      setBusy(false);
    }
  }

  const hasPin = form.lat !== null && form.lng !== null;
  return (
    <Panel
      id="map-pin"
      title="Map pin"
      description="Used for the map and the “Get directions” link on the project page."
    >
      <div className="flex flex-wrap items-start gap-3">
        <TextField
          label="Paste a Google Maps link or plus code"
          maxLength={2048}
          value={input}
          placeholder="https://maps.app.goo.gl/… or 7JWV8XX8+XX"
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              void getPin();
            }
          }}
          hint="Short plus codes like “8XX8+XX Noida” don't work: use the full code or a Maps link."
          className="flex-[1_1_320px]"
        />
        {canWrite ? (
          <Button variant="secondary" loading={busy} onClick={getPin} className="sm:mt-7.5">
            Get pin
          </Button>
        ) : null}
      </div>
      {result ? <Alert tone={result.tone}>{result.text}</Alert> : null}
      <div className="grid gap-x-5 gap-y-4 md:grid-cols-2">
        <NumberField
          label="Latitude"
          decimals={7}
          allowNegative
          value={form.lat}
          onValueChange={(lat) => setForm({ lat, ...MANUAL_PIN })}
          error={errors["location.lat"]}
          placeholder="[latitude]"
        />
        <NumberField
          label="Longitude"
          decimals={7}
          allowNegative
          value={form.lng}
          onValueChange={(lng) => setForm({ lng, ...MANUAL_PIN })}
          error={errors["location.lng"]}
          placeholder="[longitude]"
        />
      </div>
      <PinReference form={form} setForm={setForm} canWrite={canWrite} />
      <p className="text-caption text-muted">
        {hasPin ? (
          <>
            <a
              href={mapsSearchUrl(form.lat as number, form.lng as number)}
              target="_blank"
              rel="noopener noreferrer"
              className="font-bold underline"
            >
              Open in Google Maps<span className="sr-only"> (opens in a new tab)</span>
            </a>{" "}
            to check the pin is on the project entrance.
          </>
        ) : (
          "No pin yet."
        )}
      </p>
    </Panel>
  );
}
