import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type { Piece, PieceEdits } from "./types";

export const usePieces = () => useQuery({ queryKey: ["pieces"], queryFn: api.listPieces });

export const usePiece = (id: string | null) =>
  useQuery({ queryKey: ["pieces", id], queryFn: () => api.getPiece(id!), enabled: id !== null });

/** After something changed, the list is stale; a piece we were given back is already current. */
function useRefreshList() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: ["pieces"], exact: true });
}

export function useImportPiece() {
  const refresh = useRefreshList();
  return useMutation({ mutationFn: (file: File) => api.importPiece(file), onSuccess: refresh });
}

export function useSavePiece(id: string) {
  const queryClient = useQueryClient();
  const refresh = useRefreshList();
  return useMutation({
    mutationFn: (edits: PieceEdits) => api.savePiece(id, edits),
    onSuccess: (piece: Piece) => {
      queryClient.setQueryData(["pieces", id], piece);
      return refresh();
    },
  });
}

export function useReplaceScore(id: string) {
  const queryClient = useQueryClient();
  const refresh = useRefreshList();
  return useMutation({
    mutationFn: (file: File) => api.replaceScore(id, file),
    onSuccess: (piece: Piece) => {
      queryClient.setQueryData(["pieces", id], piece);
      return refresh();
    },
  });
}

export function useDeletePiece(id: string) {
  const refresh = useRefreshList();
  return useMutation({ mutationFn: () => api.deletePiece(id), onSuccess: refresh });
}
