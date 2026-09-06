import assert from "node:assert/strict";
import { test } from "node:test";

import {
  reduceCandidate,
  type CandidateReviewState,
} from "../components/research/candidate-review-state.ts";
import {
  candidateEvidenceHref,
  type CandidateEvidenceRef,
} from "../lib/api.ts";

function state(status: CandidateReviewState["status"]): CandidateReviewState {
  return { status, busy: false, error: null };
}

test("approved candidate is distinct from unreviewed candidate", () => {
  const next = reduceCandidate(state("candidate"), { type: "approve" });
  assert.equal(next.status, "approved");
});

test("rejecting a candidate records the rejected review state", () => {
  const next = reduceCandidate(state("candidate"), { type: "reject" });
  assert.equal(next.status, "rejected");
});

const baseEvidence = {
  group_chat_id: "gc-a",
  data_space: "desensitized_real",
  verification_status: "verified",
  page_or_location: "source",
  char_start: 0,
  char_end: 0,
} satisfies Partial<CandidateEvidenceRef>;

test("candidate experiment evidence opens the immutable dataset source", () => {
  process.env.NEXT_PUBLIC_API_BASE_URL = "http://api.test";
  const href = candidateEvidenceHref({
    ...baseEvidence,
    source_ref: "analysis:analysis-a",
    source_type: "experiment",
    chunk_id: null,
    document_id: null,
    analysis_id: "analysis-a",
    dataset_id: "dataset-a",
    dataset_version: 3,
    source_filename: "results.csv",
    source_url: null,
  }, "gc-fallback");

  assert.equal(
    href,
    "http://api.test/group-chats/gc-a/experiment-datasets/dataset-a/versions/3/source",
  );
  assert.equal(href?.includes("/documents/null/"), false);
});

test("candidate document and literature evidence use their own source locators", () => {
  process.env.NEXT_PUBLIC_API_BASE_URL = "http://api.test";
  const documentHref = candidateEvidenceHref({
    ...baseEvidence,
    source_ref: "chunk-a",
    source_type: "user_uploaded",
    verification_status: "pending",
    chunk_id: "chunk-a",
    document_id: "doc-a",
    analysis_id: null,
    dataset_id: null,
    dataset_version: null,
    source_filename: "source.txt",
    source_url: null,
  }, "gc-fallback");
  const literatureHref = candidateEvidenceHref({
    ...baseEvidence,
    source_ref: "literature:lead-a",
    source_type: "literature",
    chunk_id: null,
    document_id: null,
    analysis_id: null,
    dataset_id: null,
    dataset_version: null,
    source_filename: null,
    source_url: "https://doi.org/10.1000/example",
  }, "gc-fallback");

  assert.equal(documentHref, "http://api.test/documents/doc-a/download?group_chat_id=gc-a");
  assert.equal(literatureHref, "https://doi.org/10.1000/example");
});

test("candidate evidence without a valid locator is not clickable", () => {
  process.env.NEXT_PUBLIC_API_BASE_URL = "http://api.test";
  const href = candidateEvidenceHref({
    ...baseEvidence,
    source_ref: "literature:unsafe",
    source_type: "literature",
    chunk_id: null,
    document_id: null,
    analysis_id: null,
    dataset_id: null,
    dataset_version: null,
    source_filename: null,
    source_url: "javascript:alert(1)",
  }, "gc-fallback");

  assert.equal(href, null);
});
