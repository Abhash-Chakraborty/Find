import Link from "next/link";
import { ArrowRight, Lock, Sparkles, Image as ImageIcon } from "lucide-react";

export default function HomePage() {
  return (
    <div className="min-h-screen bg-white">
      {/* Hero */}
      <div className="max-w-5xl mx-auto px-6 pt-24 pb-16">
        <div className="text-center mb-16">
          <h1 className="text-6xl font-light mb-6 text-black tracking-tight">
            Find
          </h1>
          <p className="text-xl text-gray-400 mb-12 max-w-2xl mx-auto font-light">
            AI-powered image intelligence that runs entirely on your device
          </p>
          <Link
            href="/upload"
            className="inline-flex items-center gap-2 px-8 py-4 bg-black text-white text-sm hover:bg-gray-800 transition-colors"
          >
            Start Uploading
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>

        {/* Features */}
        <div className="grid md:grid-cols-3 gap-12 mt-24">
          <div>
            <div className="w-12 h-12 flex items-center justify-center mb-4">
              <Lock className="w-6 h-6 text-black" />
            </div>
            <h3 className="text-lg font-medium mb-2 text-black">
              Private by Default
            </h3>
            <p className="text-sm text-gray-400 leading-relaxed">
              All processing happens locally. Your images never leave your
              device.
            </p>
          </div>

          <div>
            <div className="w-12 h-12 flex items-center justify-center mb-4">
              <Sparkles className="w-6 h-6 text-black" />
            </div>
            <h3 className="text-lg font-medium mb-2 text-black">
              AI-Powered Search
            </h3>
            <p className="text-sm text-gray-400 leading-relaxed">
              Find images using natural language. No tagging required.
            </p>
          </div>

          <div>
            <div className="w-12 h-12 flex items-center justify-center mb-4">
              <ImageIcon className="w-6 h-6 text-black" />
            </div>
            <h3 className="text-lg font-medium mb-2 text-black">
              Smart Organization
            </h3>
            <p className="text-sm text-gray-400 leading-relaxed">
              Automatic clustering groups similar images together.
            </p>
          </div>
        </div>

        {/* Process */}
        <div className="mt-32 border-t border-gray-100 pt-16">
          <h2 className="text-2xl font-light mb-12 text-center text-black">
            How it works
          </h2>

          <div className="grid md:grid-cols-4 gap-8">
            {[
              { step: "01", title: "Upload", desc: "Drop your images" },
              { step: "02", title: "Analyze", desc: "AI processes locally" },
              { step: "03", title: "Search", desc: "Find using language" },
              { step: "04", title: "Organize", desc: "Auto-grouped clusters" },
            ].map((item) => (
              <div key={item.step}>
                <div className="text-4xl font-light text-gray-200 mb-3">
                  {item.step}
                </div>
                <h4 className="font-medium text-black mb-1">{item.title}</h4>
                <p className="text-sm text-gray-400">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
