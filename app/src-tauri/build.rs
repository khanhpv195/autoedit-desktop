fn license_config() {
  println!("cargo:rerun-if-changed=license.json");
  let raw = std::fs::read_to_string("license.json").expect("app/src-tauri/license.json is missing");
  let v: serde_json::Value = serde_json::from_str(&raw).expect("license.json is not valid JSON");
  let url = v["url"].as_str().unwrap_or("").trim().trim_end_matches('/').to_string();
  let pubkey = v["pubkey"].as_str().unwrap_or("").trim().to_string();
  if std::env::var("PROFILE").as_deref() == Ok("release") && (url.is_empty() || pubkey.is_empty()) {
    panic!("license.json has no url/pubkey: deploy license-server first (license-server/README.md)");
  }
  println!("cargo:rustc-env=AUTOEDIT_LICENSE_URL={url}");
  println!("cargo:rustc-env=AUTOEDIT_LICENSE_PUBKEY={pubkey}");
}

fn main() {
  license_config();
  tauri_build::build()
}
