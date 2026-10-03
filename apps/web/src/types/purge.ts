import { z } from 'zod';
export const purgeCountsSchema = z.object({
  mongo: z.record(z.string(), z.number()),
  r2_objects: z.number(),
  r2_bytes: z.number(),
  pinecone_vectors: z.number(),
});
export const purgePreviewSchema = z.object({
  policy_id: z.string(),
  title: z.string(),
  published: z.boolean(),
  counts: purgeCountsSchema,
  preview_token: z.string(),
  limitations: z.array(z.string()),
});
export const purgeResultSchema = z.object({
  policy_id: z.string(),
  status: z.string(),
  counts: purgeCountsSchema,
  stages: z.record(z.string(), z.string()),
  remaining: z.record(z.string(), z.number()),
  error: z.string().nullable(),
});
