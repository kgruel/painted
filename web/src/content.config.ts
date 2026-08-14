import { defineCollection } from "astro:content";
import { glob } from "astro/loaders";
import { z } from "astro/zod";

const altitude = z.enum(["paint", "compose", "lens", "cli", "live", "surface"]);

const guides = defineCollection({
  loader: glob({
    pattern: "[0-9][0-9]-*.md",
    base: "../docs/guides",
    generateId: ({ data }) => String(data.slug),
  }),
  schema: z.object({
    title: z.string(),
    summary: z.string(),
    slug: z.string(),
    order: z.number().int(),
    source: z.string(),
    prerequisite: z.object({
      label: z.string(),
      href: z.string(),
    }),
    altitudes: z.array(altitude).min(1),
    relatedDemos: z.array(z.string()).optional(),
  }),
});

export const collections = { guides };
