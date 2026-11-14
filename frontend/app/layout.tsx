import type { Metadata, Viewport } from "next";
import "./globals.css";
import Sidebar from "@/components/Sidebar";
import Footer from "@/components/Footer";

export const metadata: Metadata = {
  title: "AutoRecon",
  description: "Autonomous reconciliation and cash-flow agent",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="flex min-h-screen flex-col md:flex-row">
          <Sidebar />
          <div className="flex flex-1 flex-col overflow-y-auto">
            <main className="flex-1 p-4 md:p-8">{children}</main>
            <Footer />
          </div>
        </div>
      </body>
    </html>
  );
}
