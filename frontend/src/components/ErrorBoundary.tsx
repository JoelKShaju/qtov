import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  fallback?: string;
}

interface State {
  hasError: boolean;
}

/**
 * Catches render-time errors in its subtree (e.g. a malformed visualization spec that makes
 * ECharts' buildOption throw) so one bad chart degrades gracefully instead of blanking the app.
 * Reset it by changing `key` (we key it on the response's event_id).
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Chart render failed:", error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
          {this.props.fallback ?? "Something went wrong rendering this section."}
        </div>
      );
    }
    return this.props.children;
  }
}
