import { useQuery } from "@tanstack/react-query";
import { api } from "./client";

export const usePieces = () => useQuery({ queryKey: ["pieces"], queryFn: api.listPieces });

export const usePiece = (id: string | null) =>
  useQuery({ queryKey: ["pieces", id], queryFn: () => api.getPiece(id!), enabled: id !== null });
