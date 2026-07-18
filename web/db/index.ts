/// <reference types="@cloudflare/workers-types" />
import { env } from "cloudflare:workers";
import { drizzle } from "drizzle-orm/d1";
import * as schema from "./schema";

const bound = env as unknown as { DB: D1Database };

export function getDb() {
  if (!bound.DB) {
    throw new Error(
      "Cloudflare D1 binding `DB` is unavailable. Set the `d1` field in .openai/hosting.json to `DB` or let your control plane inject the real binding values before using the database."
    );
  }

  return drizzle(bound.DB, { schema });
}
