"use client";

import { FormEvent, useState } from "react";
import { ExternalLink, LandPlot, Loader2, MapPin, Search, Sparkles } from "lucide-react";
import { toast } from "sonner";

import { searchIndustryLocations, type LocationSearchResponse } from "@/lib/api";
import { useAuthStore } from "@/store/use-auth-store";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

const EXAMPLES = ["Textile park in Surat", "Electronics manufacturing in Tamil Nadu", "Food processing park near Indore"];

export default function LocationFinderPage() {
  const { token } = useAuthStore();
  const [query, setQuery] = useState("");
  const [response, setResponse] = useState<LocationSearchResponse | null>(null);
  const [isSearching, setIsSearching] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!token) return;
    const cleanQuery = query.trim();
    if (cleanQuery.length < 2) {
      toast.error("Enter a state, district, park, or industry sector.");
      return;
    }
    setIsSearching(true);
    try {
      setResponse(await searchIndustryLocations(cleanQuery, token));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not search industrial locations");
    } finally {
      setIsSearching(false);
    }
  }

  return (
    <div className="mx-auto w-full max-w-6xl px-5 py-8 sm:px-8">
      <div className="mb-8 max-w-3xl">
        <div className="mb-3 flex items-center gap-2 text-sm font-medium text-emerald-700">
          <MapPin className="h-4 w-4" /> Industrial park catalogue
        </div>
        <h1 className="text-3xl font-semibold tracking-tight text-zinc-900">Find a factory location</h1>
        <p className="mt-2 text-zinc-600">
          Search saved industrial parks by state, district, sector, or park name. Results are ranked from your catalogue and can include live Google Places details when configured.
        </p>
      </div>

      <Card className="border-zinc-200 shadow-sm">
        <CardContent className="p-4 sm:p-5">
          <form onSubmit={submit} className="flex flex-col gap-3 sm:flex-row">
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="e.g. food processing park in Madhya Pradesh"
              className="h-11 flex-1"
              aria-label="Search industrial locations"
            />
            <Button type="submit" disabled={isSearching} className="h-11 gap-2 bg-zinc-900 hover:bg-zinc-800">
              {isSearching ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
              Search locations
            </Button>
          </form>
          <div className="mt-3 flex flex-wrap gap-2">
            {EXAMPLES.map((example) => (
              <button key={example} type="button" onClick={() => setQuery(example)} className="rounded-full border border-zinc-200 px-3 py-1 text-xs text-zinc-600 hover:bg-zinc-50">
                {example}
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      {response && (
        <section className="mt-8">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 className="text-lg font-semibold text-zinc-900">Best matches for “{response.query}”</h2>
              <p className="text-sm text-zinc-500">Searched {response.total_catalogue_locations.toLocaleString()} saved industrial locations.</p>
            </div>
            <Badge variant="outline" className="gap-1.5 border-emerald-200 bg-emerald-50 text-emerald-700">
              <Sparkles className="h-3 w-3" />
              Google Places {response.google_places_enrichment === "enabled" ? "enabled" : "not configured"}
            </Badge>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            {response.results.map((location, index) => (
              <Card key={location.id} className="border-zinc-200">
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-wider text-zinc-400">Recommendation {index + 1}</p>
                      <CardTitle className="mt-1 text-lg leading-snug">{location.name}</CardTitle>
                    </div>
                    <Badge className="shrink-0 bg-zinc-100 text-zinc-700 hover:bg-zinc-100">{location.sector}</Badge>
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  <p className="text-sm text-zinc-600">{location.summary}</p>
                  <div className="grid grid-cols-2 gap-3 text-sm">
                    <div className="rounded-lg bg-zinc-50 p-3"><span className="block text-xs text-zinc-500">Location</span><span className="font-medium">{location.district}, {location.state}</span></div>
                    <div className="rounded-lg bg-zinc-50 p-3"><span className="block text-xs text-zinc-500">Available land</span><span className="font-medium">{location.land_available_hectares.toLocaleString()} ha</span></div>
                    <div className="rounded-lg bg-zinc-50 p-3"><span className="block text-xs text-zinc-500">Park type</span><span className="font-medium">{location.industrial_park_type || "Not specified"}</span></div>
                    <div className="rounded-lg bg-zinc-50 p-3"><span className="block text-xs text-zinc-500">Facility</span><span className="font-medium">{location.plug_and_play ? "Plug-and-play" : "Verify with authority"}</span></div>
                  </div>
                  {location.live_place && (
                    <div className="rounded-lg border border-blue-100 bg-blue-50 p-3 text-sm text-blue-950">
                      <p className="font-medium">Live Google Places information</p>
                      <p className="mt-1 text-blue-800">{location.live_place.formatted_address || location.live_place.name}</p>
                      {location.live_place.rating != null && <p className="mt-1 text-blue-800">Rating: {location.live_place.rating} ({location.live_place.user_rating_count ?? 0} reviews)</p>}
                    </div>
                  )}
                  <div className="flex flex-wrap gap-2">
                    {location.match_reasons.map((reason) => <Badge key={reason} variant="outline" className="font-normal text-zinc-600">{reason}</Badge>)}
                  </div>
                  <a href={location.maps_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 text-sm font-medium text-blue-700 hover:text-blue-900">
                    View on Google Maps <ExternalLink className="h-3.5 w-3.5" />
                  </a>
                </CardContent>
              </Card>
            ))}
          </div>
          <p className="mt-5 flex items-start gap-2 text-xs leading-5 text-zinc-500"><LandPlot className="mt-0.5 h-3.5 w-3.5 shrink-0" />{response.disclaimer}</p>
        </section>
      )}
    </div>
  );
}
