"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Field, Textarea } from "@/components/ui/Form";
import { Modal } from "@/components/ui/Modal";

/** Shared dialog for actions that take a comment or reason (approve, reject, cancel, short-close).
 *  Whether the text is required is decided by the API; `required` only marks the field. */
export function ReasonDialog({ open, title, label, confirmLabel, variant = "primary", required = true, intro, onConfirm, onClose }: {
  open: boolean;
  title: string;
  label: string;
  confirmLabel: string;
  variant?: "primary" | "danger" | "success";
  required?: boolean;
  intro?: React.ReactNode;
  onConfirm: (text: string) => Promise<boolean>; // true = done, close the dialog
  onClose: () => void;
}) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) setText(""); }, [open]);

  const submit = async () => {
    setBusy(true);
    const ok = await onConfirm(text.trim());
    setBusy(false);
    if (ok) onClose();
  };

  return (
    <Modal open={open} title={title} onClose={onClose} footer={
      <>
        <Button variant="secondary" onClick={onClose}>Cancel</Button>
        <Button variant={variant} loading={busy} onClick={submit}>{confirmLabel}</Button>
      </>
    }>
      {intro && <div className="mb-4 text-slate-600">{intro}</div>}
      <Field label={label} required={required}>
        <Textarea autoFocus value={text} onChange={(e) => setText(e.target.value)} rows={4} />
      </Field>
    </Modal>
  );
}
