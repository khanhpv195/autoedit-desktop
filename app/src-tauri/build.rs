/// Decoded length of standard base64 (with padding), None if it is not valid base64.
fn base64_decoded_len(s: &str) -> Option<usize> {
  let b = s.as_bytes();
  if b.is_empty() || !b.len().is_multiple_of(4) { return None; }
  let pad = b.iter().rev().take_while(|c| **c == b'=').count();
  if pad > 2 { return None; }
  let body = &b[..b.len() - pad];
  if !body.iter().all(|c| c.is_ascii_alphanumeric() || *c == b'+' || *c == b'/') { return None; }
  Some(b.len() / 4 * 3 - pad)
}

fn license_config() {
  println!("cargo:rerun-if-changed=license.json");
  let raw = std::fs::read_to_string("license.json").expect("app/src-tauri/license.json is missing");
  let v: serde_json::Value = serde_json::from_str(&raw).expect("license.json is not valid JSON");
  let url = v["url"].as_str().unwrap_or("").trim().trim_end_matches('/').to_string();
  let pubkey = v["pubkey"].as_str().unwrap_or("").trim().to_string();
  if std::env::var("PROFILE").as_deref() == Ok("release") {
    if url.is_empty() || pubkey.is_empty() {
      panic!("license.json has no url/pubkey: deploy license-server first (license-server/README.md)");
    }
    if !url.starts_with("https://") {
      panic!("license.json url must start with https://");
    }
    if base64_decoded_len(&pubkey) != Some(32) {
      panic!("license.json pubkey must be base64 of exactly 32 bytes (Ed25519 public key)");
    }
  }
  println!("cargo:rustc-env=AUTOEDIT_LICENSE_URL={url}");
  println!("cargo:rustc-env=AUTOEDIT_LICENSE_PUBKEY={pubkey}");
}

fn main() {
  license_config();
  tauri_build::build()
}
