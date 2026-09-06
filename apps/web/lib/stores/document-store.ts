"use client";

import { create } from "zustand";

import {
  indexDocument,
  listDocuments,
  uploadDocument,
  type DocumentRecord,
  type DocumentStatus,
} from "@/lib/api";
import { ApiConfigError, ApiError } from "@/lib/api-errors";
import { documentStatusMeta } from "@/lib/stores/document-status";

export { documentStatusMeta } from "@/lib/stores/document-status";

function errorMessage(error: unknown): string {
  if (error instanceof ApiError || error instanceof ApiConfigError) return error.message;
  return "文档请求失败，请稍后重试";
}

type DocumentStoreState = {
  groupChatId: string | null;
  documents: DocumentRecord[];
  loading: boolean;
  uploading: boolean;
  error: string | null;
  load: (groupChatId: string) => Promise<void>;
  upload: (groupChatId: string, file: File) => Promise<DocumentRecord | null>;
  index: (groupChatId: string, documentId: string) => Promise<void>;
  reset: () => void;
};

function replaceDocument(documents: DocumentRecord[], next: DocumentRecord): DocumentRecord[] {
  const existing = documents.some((document) => document.document_id === next.document_id);
  if (!existing) return [...documents, next];
  return documents.map((document) =>
    document.document_id === next.document_id ? next : document,
  );
}

export const useDocumentStore = create<DocumentStoreState>((set) => ({
  groupChatId: null,
  documents: [],
  loading: false,
  uploading: false,
  error: null,

  load: async (groupChatId) => {
    set({ groupChatId, loading: true, error: null });
    try {
      const documents = await listDocuments(groupChatId);
      set({ groupChatId, documents, loading: false });
    } catch (error) {
      set({ loading: false, error: errorMessage(error) });
    }
  },

  upload: async (groupChatId, file) => {
    set({ groupChatId, uploading: true, error: null });
    try {
      const document = await uploadDocument(groupChatId, file);
      set((state) => ({
        documents: replaceDocument(state.documents, document),
        uploading: false,
      }));
      return document;
    } catch (error) {
      set({ uploading: false, error: errorMessage(error) });
      return null;
    }
  },

  index: async (groupChatId, documentId) => {
    set({ error: null });
    try {
      const document = await indexDocument(groupChatId, documentId);
      set((state) => ({ documents: replaceDocument(state.documents, document) }));
    } catch (error) {
      set({ error: errorMessage(error) });
    }
  },

  reset: () => set({ groupChatId: null, documents: [], loading: false, uploading: false, error: null }),
}));
