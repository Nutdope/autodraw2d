import { useState, type ReactNode } from "react";

export function Section({
  title,
  children,
  defaultOpen = true,
  badge,
}: {
  title: string;
  children: ReactNode;
  defaultOpen?: boolean;
  badge?: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section className="border-b border-slate-800">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-wider text-slate-400 hover:text-slate-200"
      >
        <svg
          viewBox="0 0 16 16"
          className={`h-3 w-3 transition-transform ${open ? "rotate-90" : ""}`}
          fill="currentColor"
        >
          <path d="M5 3l6 5-6 5z" />
        </svg>
        <span className="flex-1">{title}</span>
        {badge}
      </button>
      {open && <div className="space-y-3 px-4 pb-4">{children}</div>}
    </section>
  );
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs text-slate-400">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-[11px] text-slate-500">{hint}</span>}
    </label>
  );
}

const inputCls =
  "w-full rounded-md border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-sm text-slate-100 outline-none transition focus:border-sky-500 disabled:opacity-50";

export function Select<T extends string>({
  value,
  onChange,
  options,
  disabled,
}: {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: string }[];
  disabled?: boolean;
}) {
  return (
    <select className={inputCls} value={value} disabled={disabled} onChange={(e) => onChange(e.target.value as T)}>
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

export function TextInput({
  value,
  onChange,
  placeholder,
  list,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  list?: string;
}) {
  return (
    <input
      className={inputCls}
      value={value}
      placeholder={placeholder}
      list={list}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

export function Segmented<T extends string>({
  value,
  onChange,
  options,
}: {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: string; title?: string }[];
}) {
  return (
    <div className="flex rounded-md border border-slate-700 bg-slate-900 p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          title={o.title}
          onClick={() => onChange(o.value)}
          className={`flex-1 rounded px-2 py-1 text-xs font-medium transition ${
            value === o.value ? "bg-sky-500/20 text-sky-300" : "text-slate-400 hover:text-slate-200"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Toggle({
  checked,
  onChange,
  label,
  hint,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  hint?: string;
}) {
  return (
    <label className="flex cursor-pointer items-start gap-3">
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={`relative mt-0.5 h-5 w-9 shrink-0 rounded-full transition ${checked ? "bg-sky-500" : "bg-slate-700"}`}
      >
        <span
          className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-all ${
            checked ? "left-[18px]" : "left-0.5"
          }`}
        />
      </button>
      <span className="text-sm text-slate-200">
        {label}
        {hint && <span className="block text-[11px] text-slate-500">{hint}</span>}
      </span>
    </label>
  );
}
