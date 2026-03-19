/**
 * siblings.ts — Group satellites by launch (international designator prefix).
 *
 * International designator format: YYNNNP where YY=year, NNN=launch number, P=piece.
 * Objects from the same launch share the first 5 chars (YYNNN).
 */

import type { CatalogEntry } from "../types";

/** Build an index: launch prefix (first 5 chars of intl_designator) → entries */
export function buildSiblingIndex(catalog: CatalogEntry[]): Map<string, CatalogEntry[]> {
  const index = new Map<string, CatalogEntry[]>();
  for (const entry of catalog) {
    const prefix = entry.intl_designator?.slice(0, 5);
    if (!prefix) continue;
    const group = index.get(prefix);
    if (group) {
      group.push(entry);
    } else {
      index.set(prefix, [entry]);
    }
  }
  return index;
}

/** Get sibling entries for a given NORAD ID (excluding itself). */
export function getSiblings(
  siblingIndex: Map<string, CatalogEntry[]>,
  entry: CatalogEntry | undefined,
): CatalogEntry[] {
  if (!entry?.intl_designator) return [];
  const prefix = entry.intl_designator.slice(0, 5);
  const group = siblingIndex.get(prefix);
  if (!group) return [];
  return group.filter((e) => e.norad_id !== entry.norad_id);
}
