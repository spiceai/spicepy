## Contributing to spice-py

### Developing

The development branch is `trunk`. This is the branch that all pull
requests should be made against.

To develop locally:

1. [Fork](https://help.github.com/articles/fork-a-repo/) this repository to your
   own GitHub account and then
   [clone](https://help.github.com/articles/cloning-a-repository/) it to your local device.

2. Create a new branch:

   ```
   git checkout -b MY_BRANCH_NAME
   ```

3. Install a recent version of Python (3.8+)

4. Install the dependencies with:

   ```
   # Run this command in the root of the repository
   pip install -e .
   ```

   ℹ️: Apple M1 Macs require an arm64 compatible version of pyarrow which can be installed using miniforge.

   - Install [miniforge](https://github.com/conda-forge/miniforge) using [Homebrew](https://brew.sh) with `brew install --cask miniforge`
   - Initialize the conda environment with `conda init "$(basename "${SHELL}")"`
   - Run `make apple-silicon-requirements` to install the packages.

5. Run the tests with:

   ```
   API_KEY="<Spice.xyz API Key>" make test
   ```
