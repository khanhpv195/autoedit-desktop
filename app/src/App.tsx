import { StoreProvider, useStore } from "./state/store";
import Sidebar from "./components/Sidebar";
import Onboarding from "./screens/Onboarding";

function Screen() {
  const { state } = useStore();
  const r = state.route;
  switch (r.name) {
    case "onboarding": return <Onboarding />;
    default: return <div className="view on"><h1>{r.name}</h1></div>;
  }
}

function Shell() {
  const { state } = useStore();
  if (!state.ready) return null;
  return (
    <div className="app">
      <div className="body">
        <Sidebar />
        <main className="main"><Screen /></main>
      </div>
      <div className={"toast" + (state.toast ? " on" : "")} role="status">{state.toast}</div>
    </div>
  );
}

export default function App() {
  return <StoreProvider><Shell /></StoreProvider>;
}
