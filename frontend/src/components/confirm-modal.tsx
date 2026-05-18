"use client";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

export interface PendingConfirm {
  confirmationId: string;
  tool: string;
  args: Record<string, unknown>;
  reason: string;
  preview?: string | null;
}

interface Props {
  pending: PendingConfirm | null;
  onResolve: (allow: boolean) => void;
}

export function ConfirmModal({ pending, onResolve }: Props) {
  const open = pending !== null;
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onResolve(false)}>
      <DialogContent className="max-w-2xl bg-slate-900 text-slate-100">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <span className="text-yellow-400">⚠</span>
            Confirm{" "}
            <code className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-sm text-emerald-300">
              {pending?.tool}
            </code>
          </DialogTitle>
          <DialogDescription className="text-slate-400">
            {pending?.reason || "This tool needs your approval."}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 text-sm">
          <div>
            <div className="mb-1 text-[10px] uppercase tracking-wider text-slate-500">arguments</div>
            <pre className="max-h-40 overflow-auto rounded bg-black/40 p-2 text-[11px]">
              {pending ? JSON.stringify(pending.args, null, 2) : ""}
            </pre>
          </div>

          {pending?.preview && (
            <div>
              <div className="mb-1 text-[10px] uppercase tracking-wider text-cyan-400">preview</div>
              <pre className="max-h-60 overflow-auto rounded bg-black/40 p-2 font-mono text-[11px]">
                {pending.preview.split("\n").map((line, i) => {
                  let cls = "";
                  if (line.startsWith("+")) cls = "text-emerald-300";
                  else if (line.startsWith("-")) cls = "text-red-300";
                  else if (line.startsWith("@@")) cls = "text-cyan-300";
                  return (
                    <span key={i} className={cls}>
                      {line}
                      {"\n"}
                    </span>
                  );
                })}
              </pre>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onResolve(false)} className="border-slate-700">
            Deny
          </Button>
          <Button
            onClick={() => onResolve(true)}
            className="bg-emerald-700 text-white hover:bg-emerald-600"
          >
            Allow
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
