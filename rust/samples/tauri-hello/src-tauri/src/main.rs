// desktop entry; on iOS the library's start_app (mobile_entry_point) is the entry
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    tauri_hello_lib::run()
}
