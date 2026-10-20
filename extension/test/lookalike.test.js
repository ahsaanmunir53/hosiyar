// Run with: node --test extension/test/
const test = require("node:test");
const assert = require("node:assert/strict");
const L = require("../lookalike.js");

const cases = [
  ["hbl-verify.com", "hbl"],
  ["hbl.com.secure-login.xyz", "hbl"],
  ["jazzcash-reward.xyz", "jazzcash"],
  ["easypaissa.com", "easypaisa"],
  ["bisp.gov.pk.apply-now.top", "bisp"],
  ["singapore-police-fine.com", "sg_police"],
  ["hbl.com", null],
  ["www.hbl.com", null],
  ["jazzcash.com.pk", null],
  ["echallan.psca.gop.pk", null],
  ["dawn.com", null],
  ["mom-blog.com", null],
  ["jazzfestival.com", null],
];

for (const [host, key] of cases) {
  test(`lookalike ${host}`, () => {
    const b = L.lookalike(host);
    assert.equal(b ? b.key : null, key);
  });
}

test("punycode homograph is decoded and matched", () => {
  assert.equal(L.toUnicode("xn--bl-3wc.com"), "һbl.com");
  const r = L.assess("xn--bl-3wc.com");
  assert.equal(r.reason, "homograph");
  assert.equal(r.brand.key, "hbl");
});

test("official sites get no warning", () => {
  for (const host of ["www.hbl.com", "jazzcash.com.pk", "www.nadra.gov.pk", "accounts.google.com", "web.whatsapp.com"]) {
    assert.equal(L.assess(host), null, host);
  }
});

test("registered domain handles Pakistani second-level suffixes", () => {
  assert.equal(L.registeredDomain("www.mcb.com.pk"), "mcb.com.pk");
  assert.equal(L.registeredDomain("a.b.example.org"), "example.org");
});
