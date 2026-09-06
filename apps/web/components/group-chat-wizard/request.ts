import type { CreateGroupChatRequest } from "@/lib/api";

import type { RoleDraft, WizardDraft } from "./types";

function toRoleSelection(draft: RoleDraft): CreateGroupChatRequest["member_selection"]["postdoc"] {
  return draft.mode === "existing"
    ? { selection_mode: "existing", agent_ids: draft.agentIds }
    : {
        selection_mode: "generate",
        count: draft.count,
        generate_profiles: draft.generateProfiles,
      };
}

/** Build the browser's only group-creation request for the Live workspace. */
export function buildLiveGroupChatRequest(draft: WizardDraft): CreateGroupChatRequest {
  return {
    topic_name: draft.topicName.trim(),
    topic_summary: draft.topicSummary.trim(),
    data_space: "desensitized_real",
    create_placeholder_tasks: false,
    member_selection: {
      postdoc: toRoleSelection(draft.memberSelection.postdoc),
      phd_student: toRoleSelection(draft.memberSelection.phd_student),
      master_student: toRoleSelection(draft.memberSelection.master_student),
    },
  };
}
