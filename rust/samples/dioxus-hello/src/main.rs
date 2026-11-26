//! A Dioxus mobile app built on Linux with rust/build.py (no dx): a counter.
use dioxus::prelude::*;

fn main() {
    dioxus::launch(App);
}

#[component]
fn App() -> Element {
    let mut count = use_signal(|| 0);
    rsx! {
        div { style: "font-family: -apple-system, system-ui, sans-serif; text-align: center; padding-top: 100px;",
            h1 { "Dioxus on x86Sim" }
            p { "A Dioxus mobile app built on Linux." }
            button { style: "font-size: 20px; padding: 10px 28px;", onclick: move |_| count += 1, "Count" }
            p { "Count: {count}" }
        }
    }
}
