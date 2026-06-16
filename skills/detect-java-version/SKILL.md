---
name: detect-java-version
description: Detect the Java BUILD version a Maven or Gradle project actually needs to compile (not its declared bytecode target), then start the matching JDK sandbox container (review-java-{8,11,17,21,25}-sandbox) so all read/compile/test/reproduce tooling runs under the right compiler. Use before compiling, running tests, or reproducing a bug in a Java repo — picking the wrong JDK produces false compile errors that look like code bugs.
---

# Detect a Java project's BUILD JDK, then start the right container

Goal: find the JDK under which this project actually **compiles and its tests run** — the *build floor* —
and start the matching sandbox image, so everything after runs under the correct compiler. The wrong JDK
manufactures errors that look like code bugs but aren't: `package sun.misc does not exist`, the enforcer
rejecting the Java version, `Unsupported class file major version N`. Detect once, up front, then build.

## The one rule that matters
**The declared level is the bytecode TARGET, not the build floor.** `maven.compiler.source/target/release`,
Gradle `sourceCompatibility` / `toolchain.of(N)` only say *what bytecode to emit* — a project can declare
8 and still need JDK 11+ to build (a plugin, codegen, or enforcer demands it). Real example: quarkus 1.x
declares `source 1.8` yet builds on JDK 11, and won't compile on 21 (`sun.misc` removed, enforcer rejects).
So read the declared level as a **starting guess**, then **confirm by compiling**.

## 1. Identify the build tool
- root `pom.xml` → **Maven** (prefer `./mvnw` if present).
- `build.gradle`/`.kts` + `gradlew`, no pom → **Gradle** (always the repo's `./gradlew`, never system gradle).

## 2. Read the declared signals → an initial guess `g`
Collect every Java level you can find; take the **max** as `g`:
- **Maven:** `maven.compiler.release|source|target`, `<java.version>`, `maven-compiler-plugin <release>`,
  and especially the enforcer `requireJavaVersion` range (a real build floor when present), `.mvn/jvm.config`.
- **Gradle:** `sourceCompatibility`/`targetCompatibility`/`options.release`, `JavaLanguageVersion.of(N)`,
  Kotlin `jvmToolchain(N)`; the Gradle **wrapper** version (it gates which JDK can even run — see §3).
- **Either:** `.sdkmanrc`, `.tool-versions`, CI (`.github/workflows/*` `java-version:`), Dockerfiles.

Class-file → JDK map (to read `Unsupported class file major version N`): **v52=8, v55=11, v61=17, v65=21, v69=25**.

## 3. Confirm by compiling — the floor is whatever actually builds
Try candidate JDKs in ascending order starting from `g`, among the available images {8,11,17,21,25}, each in
its container:
- **Maven:** `JAVA_HOME=<jdk> mvn -B -ntp -DskipTests compile`
- **Gradle:** `JAVA_HOME=<jdk> ./gradlew testClasses` — first bump the wrapper if it predates the JDK
  (floors: JDK 11→Gradle 5, 17→7.3, 21→8.5, 25→9.0; an old wrapper fails to even start with
  `Could not determine java version` / `Unsupported class file major version` while *configuring*).

The **lowest JDK that compiles clean** is the build floor → start its image.

Read the failures correctly (these are *which JDK*, not code bugs):
- `package sun.misc does not exist`, enforcer `enforce-java-version` fails → JDK too **NEW** → try lower.
- `package javax.xml.bind…`, `tools.jar`/`com.sun:tools` → EE/tools removed in 11 → either JDK too new, or
  the project genuinely needs JDK **8**, or re-add the EE deps (then 11+ works).
- Lombok `JCTree.qualid` / `TypeTag::UNKNOWN`, or `Unsupported class file major version > g` → the
  *toolchain* (Lombok/ASM/ByteBuddy) is too old for this JDK — not a JDK-choice error; fix the tool. (Full
  symptom→fix table: the `bump-java-version-skill` §7.)

## 4. Start the matching container, then use it for everything
Map the build floor to its image and start it:
`review-java-8-sandbox | -11- | -17- | -21- | -25-`. Run all subsequent read/compile/test/reproduce tooling
**inside that container** — reading and compiling share the one mounted checkout under the right JDK.

## Quick default when probing isn't worth it
- Old code (source ≤ 8, `javax.*`, `sun.misc`) → start at **JDK 11**: it compiles 8-level code, keeps
  `sun.misc`, and satisfies the common "11+" enforcers. Drop to **JDK 8** only if 11 fails on a removed API
  the project can't re-add.
- Modern code → the image for its declared level (12–17→17, 18–21→21, 22–25→25).

Once the JDK is chosen and the project still won't build for a *toolchain* reason, follow
`bump-java-version-skill` for the deterministic fixes (Lombok floor, EE deps, surefire/Mockito/ByteBuddy/
JaCoCo bumps, `--add-opens`).
