"use client";

import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

/**
 * Catches any Three.js / WebGL / render errors from FactoryCanvas
 * and renders a friendly fallback instead of a blank white page.
 */
export class FactoryErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[FactoryCanvas] 3D render error caught by boundary:", error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;
      return (
        <div className="flex h-full w-full flex-col items-center justify-center gap-4 bg-[#060b16] text-center px-8">
          <div className="rounded-2xl border border-red-500/30 bg-red-500/10 p-6 max-w-md">
            <p className="text-2xl mb-2">⚠️</p>
            <p className="text-sm font-bold text-red-400 mb-1">3D Rendering Error</p>
            <p className="text-xs text-slate-400 leading-relaxed">
              Your browser&apos;s WebGL context could not render the factory scene.
            </p>
            {this.state.error && (
              <p className="mt-2 text-[10px] text-red-400/60 font-mono bg-red-500/5 rounded p-2 text-left break-all">
                {this.state.error.message}
              </p>
            )}
            <button
              onClick={() => this.setState({ hasError: false, error: null })}
              className="mt-4 rounded-lg bg-red-500/20 border border-red-500/30 px-4 py-2 text-xs font-bold text-red-300 hover:bg-red-500/30 transition-colors"
            >
              Try Again
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
