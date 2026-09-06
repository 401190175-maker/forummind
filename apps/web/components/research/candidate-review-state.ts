type CandidateStatus = "candidate" | "approved" | "rejected";

export type CandidateReviewState = {
  status: CandidateStatus;
  busy: boolean;
  error: string | null;
};

export type CandidateReviewAction =
  | { type: "start" }
  | { type: "approve" }
  | { type: "reject" }
  | { type: "error"; message: string };

export function reduceCandidate(
  state: CandidateReviewState,
  action: CandidateReviewAction,
): CandidateReviewState {
  if (action.type === "start") return { ...state, busy: true, error: null };
  if (action.type === "approve") return { status: "approved", busy: false, error: null };
  if (action.type === "reject") return { status: "rejected", busy: false, error: null };
  return { ...state, busy: false, error: action.message };
}
