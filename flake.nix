{
  description = "Dev shell for the e-ink dashboard render server (Playwright + Python)";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";
  };

  outputs =
    { nixpkgs, ... }:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs { inherit system; };
      python = pkgs.python3.withPackages (ps: [
        ps.playwright
        ps.jinja2
        ps.flask
        ps.pillow
      ]);
    in
    {
      devShells.${system}.default = pkgs.mkShell {
        packages = [ python ];
        shellHook = ''
          export PLAYWRIGHT_BROWSERS_PATH=${pkgs.playwright-driver.browsers}
          export PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
        '';
      };
    };
}
