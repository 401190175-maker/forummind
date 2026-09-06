/**
 * 群聊输入区、`@` 选择、任务澄清与面板状态的统一前端类型
 * （design.md §4.1，tasks.md Task 1）。
 *
 * 只定义类型，不包含 React 组件代码；各组件从本模块导入，
 * 避免重复定义结构。
 */

/** `@` 可选对象：全体成员、某类角色、具体成员（design §4.1）。 */
export type MentionTarget =
  | { type: "all"; id: "all"; label: "全体成员" }
  | { type: "role"; id: string; label: string; role: string }
  | { type: "member"; id: string; label: string; role: string };

/** 群聊输入框草稿：文本 + 可选的 `@` 对象。 */
export type ComposerDraft = {
  text: string;
  mention: MentionTarget | null;
};

/** 苏格拉底式澄清问题（单条）。 */
export type ClarificationQuestion = {
  id: string;
  speaker: string;
  content: string;
};

/** 已完成的一轮澄清问答。 */
export type ClarificationTurn = {
  questionId: string;
  question: string;
  answer: string;
};

/** 任务澄清草稿：被点名对象先提问，澄清完成前不生成正式任务。 */
export type TaskClarificationDraft = {
  id: string;
  mention: MentionTarget;
  initialIntent: string;
  turns: ClarificationTurn[];
  currentQuestion: ClarificationQuestion | null;
  questionCount: number;
  maxQuestions: 7;
  status: "awaiting_answer" | "ready_to_assign" | "failed";
  error?: string;
};
