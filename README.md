# Vertex AI SDK Test Data
The Vertex AI SDK Test Data includes mock responses from Gemini models for use
in unit testing of the Vertex AI for Firebase SDKs.

## Usage
The mock responses are currently being used to test the Vertex AI for Firebase
SDKs in the following repositories:
- [firebase-ios-sdk](https://github.com/firebase/firebase-ios-sdk/)
- [firebase-js-sdk](https://github.com/firebase/firebase-js-sdk/)

## Versioning
All commits affecting the [mock-responses](mock-responses) directory will be
tagged by GitHub Actions with version numbers of the format `v<MAJOR>.<MINOR>`
following these guidelines:
- Changes to existing mock response files require a **major** version bump.
- Introduction of new mock response files require a **minor** version bump.
- There is no "patch" version.
