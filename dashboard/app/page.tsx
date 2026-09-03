import Link from "next/link";

const DEMO_NUMBER_DISPLAY = "+1 (339) 244-8277";
const DEMO_NUMBER_TEL = "+13392448277";

export default function ShowcasePage() {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b-[10px] border-brand bg-ink text-white">
        <div className="mx-auto flex max-w-page items-baseline justify-between px-6 py-3">
          <span className="text-xl font-bold tracking-tight">CallSentry</span>
          <Link href="/login" className="link text-white hover:text-white">
            Sign in
          </Link>
        </div>
      </header>

      <main className="mx-auto w-full max-w-page flex-1 px-6 py-16 sm:py-24">
        <div className="max-w-3xl">
          <h1 className="text-[2.75rem] font-bold leading-[1.05] tracking-tight sm:text-[3.5rem]">
            Every call answered. Nothing slips through.
          </h1>
          <p className="mt-6 max-w-2xl text-xl leading-relaxed">
            CallSentry answers the phone for your business, books appointments, and hands
            anything it cannot resolve to a person. It runs on your own hardware.
          </p>

          <section className="mt-14 border-l-[10px] border-brand pl-6" aria-labelledby="demo">
            <h2 id="demo" className="text-base font-bold uppercase tracking-wide text-secondary">
              Demo
            </h2>
            <p className="mt-2 text-2xl leading-snug sm:text-3xl">
              Call{" "}
              <a href={`tel:${DEMO_NUMBER_TEL}`} className="link whitespace-nowrap font-bold tabular-nums">
                {DEMO_NUMBER_DISPLAY}
              </a>{" "}
              and experience CallSentry.
            </p>
            <p className="mt-3 text-base text-secondary">
              Ask a question, book an appointment, or give it something it can&apos;t answer.
            </p>
          </section>

          <p className="mt-14 text-lg">
            <Link href="/login" className="link font-bold">
              View the dashboard
            </Link>
          </p>
        </div>
      </main>

      <footer className="border-t border-border bg-canvas">
        <div className="mx-auto max-w-page px-6 py-6 text-sm text-secondary">
          CallSentry · self-hosted voice receptionist
        </div>
      </footer>
    </div>
  );
}
