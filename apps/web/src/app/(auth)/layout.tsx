import { Logo } from "@/components/logo";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid min-h-screen lg:grid-cols-[1.1fr_1fr]">
      <div className="relative hidden overflow-hidden bg-[#0b1f3a] p-12 text-white lg:flex lg:flex-col">
        <Logo light />
        <div className="mt-auto max-w-lg">
          <div className="mb-4 h-px w-16 bg-[#c9a227]" />
          <h2 className="text-3xl font-semibold leading-tight tracking-tight">
            Underwrite with the rigor of an investment committee — at the speed of software.
          </h2>
          <p className="mt-4 text-sm leading-relaxed text-white/70">
            Source-referenced document intelligence, deterministic financial engines and auditable outputs.
            AI interprets and explains; validated mathematics calculates.
          </p>
          <dl className="mt-10 grid grid-cols-3 gap-6 border-t border-white/10 pt-6 text-sm">
            <div>
              <dt className="text-white/50">Engine tests</dt>
              <dd className="mt-1 text-lg font-semibold text-[#c9a227]">100% coverage</dd>
            </div>
            <div>
              <dt className="text-white/50">10-yr model</dt>
              <dd className="mt-1 text-lg font-semibold text-[#c9a227]">&lt; 5 ms</dd>
            </div>
            <div>
              <dt className="text-white/50">Every figure</dt>
              <dd className="mt-1 text-lg font-semibold text-[#c9a227]">Traceable</dd>
            </div>
          </dl>
        </div>
        <svg className="pointer-events-none absolute -right-24 -top-24 size-[480px] opacity-[0.07]" viewBox="0 0 100 100" aria-hidden>
          <path d="M50 5 L95 90 H75 L50 40 L25 90 H5 Z" fill="#c9a227" />
        </svg>
      </div>
      <div className="flex items-center justify-center p-6">
        <div className="w-full max-w-sm">
          <div className="mb-8 lg:hidden">
            <Logo />
          </div>
          {children}
        </div>
      </div>
    </div>
  );
}
