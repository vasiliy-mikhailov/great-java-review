### 1. beikov — hibernate/hibernate-orm#11391  (rubric=4, pts=5)
PR: PR #11391: HHH-19826 Add array_reverse and array_sort functions
REVIEW: SUMMARY: Can you also please do the simplifications I proposed across all three emulations? POINTS: - [hibernate-core/src/main/java/org/hibernate/dialect/function/array/H2ArraySortFunction.java:100] It would make the code later more readable if you default the `nullsFirstNode` here already. ```suggestion : descendingNode; ``` - [hibernate-core/src/main/java/org/hibernate/dialect/function/array/H2ArraySortFunction.java:97] This is only called when at least the `descending` flag is passed, so let's make this easier. ```suggestion assert sqlAstArguments.size() >= 2; final Expression arrayExpressi

### 2. laeubi — eclipse-tycho/tycho#3295  (rubric=4, pts=4)
PR: PR #3295: Restoring the option to ignore p2 mirrors via the Maven settings
REVIEW: POINTS: - [p2-maven-plugin/pom.xml:210] p2 plugin should not depend on tycho-core - [p2-maven-plugin/src/main/java/org/eclipse/tycho/p2maven/transport/RemoteArtifactRepositoryManagerAgentFactory.java:39] please use `LegacySupport` to access the session directly to get its properties - [p2-maven-plugin/src/main/java/org/eclipse/tycho/p2maven/transport/RemoteArtifactRepositoryManagerAgentFactory.java:53] its seems a good idea to refactor this and the follogiwn check into a method that: 1. first check for the property in the System.getProperty 2. then if we have a session 3. if session the use sy

### 3. franz1981 — netty/netty#15624  (rubric=4, pts=1)
PR: PR #15624: Expose metrics from AutoScalingEventExecutorChooserFactory
REVIEW: POINTS: - [common/src/main/java/io/netty/util/concurrent/AutoScalingEventExecutorChooserFactory.java:80] It's a set release, basically, which can establish a happens before and synchronize with relation, if paired by a get acquire/get volatile

### 4. wilkinsona — spring-projects/spring-boot#49838  (rubric=5, pts=11)
PR: PR #49838: fix: don't delegate client alias choosing for ssl bundles
REVIEW: POINTS: - [core/spring-boot/src/main/java/org/springframework/boot/ssl/SslBundleKey.java:52] This should be deprecated for removal in 4.3.0 in favor of `getServerAlias()` and `getClientAlias()`. - [core/spring-boot/src/main/java/org/springframework/boot/ssl/SslBundleKey.java:58] This should be marked as `@since 4.1.0` - [core/spring-boot/src/main/java/org/springframework/boot/ssl/SslBundleKey.java:67] This should be marked as `@since 4.1.0` - [core/spring-boot/src/main/java/org/springframework/boot/ssl/SslBundleKey.java:168] This should be marked as `@since 4.1.0`. - [core/spring-boot/src/main

### 5. HeikoKlare — eclipse-platform/eclipse.platform.swt#2927  (rubric=4, pts=5)
PR: PR #2927: Using ImageHandleManager for managing multiple Image handles in Image 
REVIEW: SUMMARY: The changes look like a good refactoring to better encapsulate the management of handles for zooms and in general are fine fore me. I still have some proposals for improvements. POINTS: - [bundles/org.eclipse.swt/Eclipse SWT/win32/org/eclipse/swt/graphics/Image.java:142] Since this is to a certain degree a wrapper for a data structure map, wouldn't it maybe be sufficient to use according short method names rather than always repeating "handle" and "imageHandle"? I.e.: - getImageHandle(zoom) -> get(zoom) - getHandleOrCreate(zoom, creator) -> getOrCreate(zoom, creator) - hasImageHandle(

### 6. lhotari — apache/pulsar#21885  (rubric=4, pts=1)
PR: PR #21885:  [fix] [broker] Fix break change: could not subscribe partitioned top
REVIEW: POINTS: - [pulsar-broker/src/test/java/org/apache/pulsar/broker/auth/MockedPulsarServiceBaseTest.java:730] This breaks Pulsar SQL / Trino tests in branch-3.1 and before. I created #21976 to address the problem.

### 7. dmlloyd — quarkusio/quarkus#13102  (rubric=4, pts=1)
PR: PR #13102: Make isTraceEnabled calls be computed at build time #12938
REVIEW: POINTS: - [core/runtime/src/main/java/io/quarkus/runtime/logging/CategoryBuildTimeConfig.java:18] We had effectively this feature in the `min-level` configuration. Filtering out arbitrary levels doesn't seem as specifically useful as setting a single bound (and might lead to some confusion). It certainly would be more complex to implement.

### 8. laeubi — eclipse-tycho/tycho#5401  (rubric=5, pts=1)
PR: PR #5401: Migrate all @Component annotated classes to JSR330 annotations
REVIEW: POINTS: - [demo/bnd-workspace/tycho.demo.consumer/src/main/java/org/eclipse/tycho/demo/consumer/Consumer.java:21] @copilot this is not a maven annotation, this is a [declarative services annotation](https://docs.osgi.org/specification/osgi.cmpn/7.0.0/service.component.html) and should not be migrated!

### 9. yersan — wildfly/wildfly-core#6741  (rubric=4, pts=2)
PR: PR #6741: [WFCORE-7576] do not use JAVA_OPTS or GC_LOG options with standalone.s
REVIEW: SUMMARY: Thanks @aogburn , added two comments and want to get your feedback Optionally, we could also add a test at testsuite/scripts/src/test/java/org/wildfly/scripts/test/ to verify the server starts with the version argument and verifies the JAVA_OPTS or PROCESS_CONTROLLER_JAVA_OPTS are not changed, but it is optional to me, I am not sure if the `ScriptTestCase` base test class is prepared for a test like this one. @jamezp could you also add your feedback to this PR? POINTS: - [core-feature-pack/common/src/main/resources/content/bin/domain.sh:29] I think it is ok since it makes the script m

### 10. muralibasani — apache/kafka#22279  (rubric=4, pts=1)
PR: PR #22279: MINOR: Enable testNoDescribeProduceOrConsumeWithoutTopicDescribeAcl f
REVIEW: POINTS: - [clients/src/main/java/org/apache/kafka/clients/consumer/internals/ConsumerUtils.java:274] It could be possible to have CompletionException has nested CompletionExceptions or an ExecutinException, and they are never reached. May be a multi-level unwrap is better?

### 11. laeubi — eclipse-platform/eclipse.platform.swt#1395  (rubric=4, pts=1)
PR: PR #1395: Handle local resource references in Edge#setText()
REVIEW: POINTS: - [bundles/org.eclipse.swt/Eclipse SWT Browser/win32/org/eclipse/swt/browser/Edge.java:940] The API claims that the location is always a valid URI, so anything passed in here that is not an URI must return false.

### 12. romani — sevntu-checkstyle/sevntu.checkstyle#742  (rubric=4, pts=1)
PR: PR #742: Issue #734: New check 'Jsr305AnnotationsCheck'
REVIEW: POINTS: - [sevntu-checks/src/main/java/com/github/sevntu/checkstyle/checks/coding/Jsr305AnnotationsCheck.java:48] please add few(1-2) examples (with inlined comments of where is violation) to Javadoc, user do like examples more documentation. example - https://checkstyle.org/config_annotation.html#AnnotationLocation_Examples https://github.com/checkstyle/checkstyle/blob/master/src/main/java/com/puppycrawl/tools/checkstyle/checks/annotation/AnnotationLocationCheck.java#L91

### 13. raunaqmorarka — trinodb/trino#29171  (rubric=5, pts=1)
PR: PR #29171: Add CLAUDE.md with guidance for AI coding assistants
REVIEW: POINTS: - [CLAUDE.md:35] Also tested — created a file with `if (x > 0) System.out.println("hi");`, ran `mcp__idea__reformat_file`, and the braces were not added. Same reason as the wildcard case: the MCP tool runs plain Reformat Code, not Reformat and Cleanup. Your IDE likely has "Reformat and Cleanup" bound or code cleanup enabled in the reformat dialog, but that doesn't carry over when Claude invokes the formatter through the MCP. Keeping the bullet.

### 14. franz1981 — netty/netty#15399  (rubric=4, pts=1)
PR: PR #15399: Introduce size-classes for the adaptive allocator
REVIEW: POINTS: - [buffer/src/main/java/io/netty/buffer/AdaptivePoolingAllocator.java:248] Actually if we know the last/max value we should check that one first ^^ to avoid the log2(n) useless checks. If it is stored in a static final field will be trusted and it won't cost like reaching first the array base + offset of position

### 15. franz1981 — netty/netty#15452  (rubric=5, pts=1)
PR: PR #15452: Improved bound checks
REVIEW: POINTS: - [microbench/src/main/java/io/netty/buffer/ByteBufAccessBenchmark.java:184] And checking the JMH samples from shipilev seems that what we got in the other test (e.g. the sum) is not right: https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_34_SafeLooping.java#L128

### 16. laeubi — eclipse-platform/eclipse.platform.swt#1026  (rubric=4, pts=2)
PR: PR #1026: Expose cancel state of FileDialog and DirectoryDialog
REVIEW: SUMMARY: It looks fine for me just a bit unsure about the naming but maybe others like to give advice. POINTS: - [bundles/org.eclipse.swt/Eclipse SWT/win32/org/eclipse/swt/widgets/DirectoryDialog.java:216] ```suggestion return Optional.ofNullable(directoryPath); ``` could it be null? or maybe the case of empty should also result in a Optional.empty().... - [bundles/org.eclipse.swt/Eclipse SWT/win32/org/eclipse/swt/widgets/DirectoryDialog.java:153] ```suggestion public Optional<String> openDirectory() { ``` What do you think about something like this? askSelect sounds a bit strange and that way

### 17. lhotari — apache/pulsar#22799  (rubric=5, pts=4)
PR: PR #22799: [improve] PIP-381: Handle PositionInfo that's too large to serialize 
REVIEW: SUMMARY: I added a few review comments. POINTS: - [managed-ledger/src/main/java/org/apache/bookkeeper/mledger/impl/ManagedCursorImpl.java:688] instead of adjusting the writerIndex manually, `buffer.addComponent(true, part)` could be a way to achieve this. - [managed-ledger/src/main/java/org/apache/bookkeeper/mledger/impl/ManagedCursorImpl.java:3509] use `.addComponent(true, szBuf).addComponent(true, encode)` so that there isn't a need to set the writerIndex manually. - [managed-ledger/src/main/java/org/apache/bookkeeper/mledger/impl/MetaStoreImpl.java:466] When using LightProto, the buffer sho

### 18. HeikoKlare — eclipse-platform/eclipse.platform.swt#1767  (rubric=4, pts=1)
PR: PR #1767: Replace and deprecate Image creating methods accepting Strings as file
REVIEW: POINTS: - [bundles/org.eclipse.swt/Eclipse SWT/common/org/eclipse/swt/graphics/ImageFileProvider.java:30] From my point of view, the disadvantage is that it prevents you from declaring a method properly reflecting its semantics (like the current `getImagePath(zoom)`) and gives you a meaningless `apply(value)` instead. Functional interfaces make sense for defining lambas or other anonynous types, but not being implemented by an actual interface or class as usually they are too generic to actually use their methods in a proper OO way.

### 19. radcortez — smallrye/smallrye-config#1270  (rubric=5, pts=3)
PR: PR #1270: check duplicate keys
REVIEW: SUMMARY: Thank you for the PR. I've left a few comments. POINTS: - [documentation/src/main/docs/config/getting-started.md:58] I think we don't need an extra configuration to warn / fail. A simple warning should be enough. - [implementation/src/main/java/io/smallrye/config/ConfigValueConfigSource.java:409] `.put` returns the previous object associated with the key. It can easily be used to check and warn about the old and new values. - [implementation/src/main/java/io/smallrye/config/ConfigValuePropertiesUtils.java:21] If we don't use a configuration to warm / fail and use `.put` semantics, thi

### 20. beikov — hibernate/hibernate-orm#11834  (rubric=4, pts=1)
PR: PR #11834: HHH-19759 Fix HQL join key() for maps with basic-typed keys
REVIEW: POINTS: - [hibernate-core/src/main/java/org/hibernate/query/hql/internal/QualifiedJoinPathConsumer.java:228] Might be good to add a test to ensure fetch join doesn't work. ```suggestion if ( !fetch && lhs instanceof PluralJoin ) { ```

### 21. franz1981 — netty/netty#15524  (rubric=4, pts=1)
PR: PR #15524: Implement automatic scaling for EventLoopGroup threads
REVIEW: POINTS: - [transport-classes-kqueue/src/main/java/io/netty/channel/kqueue/KQueueIoHandler.java:263] we should have a `context.shouldReportActiveIoTime` to decide if collecting `System::nanoTime`

### 22. mkouba — quarkusio/quarkus#54362  (rubric=4, pts=1)
PR: PR #54362: Make Qute's ValueResolverGenerator deterministic for binary reproduci
REVIEW: POINTS: - [independent-projects/qute/generator/src/main/java/io/quarkus/qute/generator/ValueResolverGenerator.java:784] > If we want to go with the ArC approach, we probably need a shared utility for reproducibility somewhere. Yes, I think that it would be useful but since `Reproducibility` lives in `arc-processor` we would have to move the common logic in a new artifact. For now, we could just copy the [`Reproducibility#orderedMethods()`](https://github.com/quarkusio/quarkus/blob/main/independent-projects/arc/processor/src/main/java/io/quarkus/arc/processor/Reproducibility.java) into the `qut

### 23. lhotari — apache/pulsar#25126  (rubric=5, pts=1)
PR: PR #25126: [improve][cli] Add client side looping in "pulsar-admin topics analyz
REVIEW: POINTS: - [pulsar-client-tools/src/main/java/org/apache/pulsar/admin/cli/CmdTopics.java:3016] --backlog-scan-max-entries default of -1 relies on a subtle side-effect for backward compat — CmdTopics.java:3019 With -1, the predicate result.getEntries() >= -1 is always true, so the loop completes on the first iteration (matching old single-call behavior). That works, but it conflates "unset" with "terminate immediately." Preferred: treat unset as "no cap" (use the no-predicate overload analyzeSubscriptionBacklogAsync(topic, sub, pos)) and only take the looping path when -b is supplied. That makes

### 24. keith-turner — apache/accumulo-fluo#1004  (rubric=5, pts=1)
PR: PR #1004: FLUO-1000 OracleServer race conditions
REVIEW: POINTS: - [modules/core/src/main/java/org/apache/fluo/core/oracle/OracleServer.java:199] That post is correct. However in this situation, the method is private and only called by a synchronized public method. Therefore nothing external can directly call the method in an unsynchronized way. It would be fine to make the whole method synchronized if you think that makes the code more clear.

### 25. rock3r — JetBrains/intellij-community#3384  (rubric=5, pts=5)
PR: PR #3384: [JEWEL-1212] Calculate ComboBox Popup Height Based on maxPopupRowCount
REVIEW: SUMMARY: ![](https://media1.giphy.com/media/v1.Y2lkPTc5MGI3NjExc2l6NGt2cGd4Nng5aGhlemMxN3RobWF6cGVnN2Z2YzBsZXN6dW4zaSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/OKvq25SbsTURpQOSWS/giphy.gif) POINTS: - [platform/jewel/int-ui/int-ui-standalone/src/main/kotlin/org/jetbrains/jewel/intui/standalone/styling/IntUiComboBoxStyling.kt:221] Shouldn't we deprecate-and-hide this? - [platform/jewel/int-ui/int-ui-standalone/src/main/kotlin/org/jetbrains/jewel/intui/standalone/styling/IntUiComboBoxStyling.kt:228] No maxPopupRowCount here? - [platform/jewel/int-ui/int-ui-standalone/api-dump.txt:122] I think this 

### 26. yersan — wildfly/wildfly-core#5947  (rubric=5, pts=1)
PR: PR #5947: [WFCORE-6755] Move the org.wildfly.security:wildfly-elytron-dynamic-ss
REVIEW: POINTS: - [elytron/src/main/java/org/wildfly/extension/elytron/ElytronDefinition.java:366] In any case, @Skyllarr notice that what you are checking there is if the resourceRegistration enables the `community` stability. That's not what we would need to check, we would need to check whether the resourceRegistration enables the current stability where the server is running at runtime. So, if you launch your server with `default` stability, your additional package won't be required to be registered.

### 27. muralibasani — apache/kafka#22203  (rubric=4, pts=1)
PR: PR #22203: KAFKA-18389: Preserve votedKey when transitioning to leader state
REVIEW: POINTS: - [raft/src/main/java/org/apache/kafka/raft/LeaderState.java:696] there seems to be no test for this returning of votedKey. I think that would be better

### 28. raunaqmorarka — trinodb/trino#29249  (rubric=4, pts=2)
PR: PR #29249: Add unit testing for orphan file removal
REVIEW: SUMMARY: lgtm, minor comments POINTS: - [plugin/trino-iceberg/src/main/java/io/trino/plugin/iceberg/IcebergMetadata.java:2563] `@VisibleForTesting` - [plugin/trino-iceberg/src/test/java/io/trino/plugin/iceberg/TestRemoveOrphanFiles.java:73] Can you go through the remove_orphan_files tests in BaseIcebergConnectorTest or elsewhere and see if some of them can be deleted due to being redundant or converted into unit tests here ? Ideally I would like the complexities of the internal logic of remove_orphan_files to be tested here, while the query runner tests verify the SQL interface.

### 29. lhotari — apache/pulsar#19975  (rubric=5, pts=1)
PR: PR #19975: [refactor][fn] Use AuthorizationServer more in Function Worker API
REVIEW: POINTS: - [pulsar-functions/worker/src/main/java/org/apache/pulsar/functions/worker/rest/api/WorkerImpl.java:129] this looks risky since the else branch doesn't throw an exception or verify that authorization/authentication is disabled

### 30. HannesWell — eclipse-platform/eclipse.platform.swt#1045  (rubric=5, pts=1)
PR: PR #1045: Compile SWT natives for Windows on Arm64 (WoA).
REVIEW: POINTS: - [Jenkinsfile:65] > @HannesWell I don't think this "aarch64 replacement" with the x86_64 equivalent will work; it may work for the compiling step, but will certainly fail during linking due to mismatched native libs. If it does work during linking, which I very much doubt it, then the resulting `.dll` files won't work at runtime on a Windows Arm64 box. Yes. As we can see in the logs of the latest build you anticipated it right and it does not even build. But this was just temporary to reach the the part of the pipeline where the new native agent is contacted and to test its very basic

### 31. romani — sevntu-checkstyle/sevntu.checkstyle#827  (rubric=4, pts=1)
PR: PR #827: Issue #826: Support AssertJ/Google Truth fail() methods in RequireFailF
REVIEW: POINTS: - [sevntu-checks/src/main/java/com/github/sevntu/checkstyle/checks/coding/RequireFailForTryCatchInJunitCheck.java:127] @sebthom , please update javadoc with new methods to detect. javadoc is the only way for user to read what Check is doing.

### 32. wilkinsona — spring-projects/spring-boot#42443  (rubric=5, pts=0)
PR: PR #42443: Support service connections with RabbitMQ Streams and Testcontainers
REVIEW: SUMMARY: > when rabbitmq_stream plugin is enabled Apologies if I've missed it, but I can't see any code in the connection details factory that checks that the stream plugin is enabled. What'll happen if the factory kicks in on a container without streams enabled? I'm wondering if it may break somehow, perhaps by overriding the app's Rabbit Streams configuration with connection details that won't work.

### 33. franz1981 — eclipse-vertx/vert.x#5048  (rubric=5, pts=1)
PR: PR #5048: Context local storage SPI
REVIEW: POINTS: - [src/main/java/io/vertx/core/impl/ContextBase.java:60] We don't need atomicity here, but the same semantic of putLocal, which doesn't care of races, imo. If we need that level of atomicity we can have a new method which ensure an atomic change and use the compare and set.

### 34. mickaelistria — eclipse-platform/eclipse.platform.swt#67  (rubric=5, pts=1)
PR: PR #67: Let Display implement java.util.concurrent.Executor
REVIEW: POINTS: - [bundles/org.eclipse.swt/Eclipse SWT/gtk/org/eclipse/swt/widgets/Display.java:2427] You're more motivating me to audit why some many Display.getDefault() in Platform than convincing me we need some static stuff on Display object. I see a difference that most APIs in futures are written as utility or services and are hiding the implicit executor. But here the Display is more an object, and there can easily be multiple ones. If display implements `Executor` already, one can write `future.thenAcceptAsync(widget::setText, widget.getDisplay())`, or `future.thenAcceptAsync(res -> findWidge

### 35. yersan — wildfly/wildfly-core#6175  (rubric=4, pts=1)
PR: PR #6175: [WFCORE-6994] Add ModelTestControllerVersion.EAP_XP_5
REVIEW: POINTS: - [model-test/src/main/java/org/jboss/as/model/test/ModelTestControllerVersion.java:24] > Also, I wonder, won't be necessary to have the expected controllers available from https://github.com/wildfly/wildfly-legacy-test/? Ok, I think I partially got this, it is using model controllers for `29.0.0`, which were introduced in `EAP_8_0_0`, so there is no need to add new ones in https://github.com/wildfly/wildfly-legacy-test. The only pending detail is about resources as https://github.com/wildfly/wildfly-legacy-test/blob/main/tools/src/main/resources/legacy-models/standalone-resource-defin

### 36. raunaqmorarka — trinodb/trino#29171  (rubric=5, pts=1)
PR: PR #29171: Add CLAUDE.md with guidance for AI coding assistants
REVIEW: POINTS: - [CLAUDE.md:3] Strengthened the imperative — bolded "you must first read", added "in full" to directly counter the reads-first-and-last-5-lines symptom, and spelled out the consequence ("skipping the read means missing them"). On `@path` imports specifically: verified from the [Claude Code docs](https://code.claude.com/docs/en/memory#import-additional-files) that `@` is a full import — it pulls the file's contents into context at launch, not just a hint to read. Applied to `DEVELOPMENT.md` (~300 lines, much of it unrelated to code style like Web UI build, release process, Vector API) 

### 37. vietj — eclipse-vertx/vert.x#4494  (rubric=4, pts=1)
PR: PR #4494: Add GlobalTrafficShapingHandler to server pipeline for bandwidth limit
REVIEW: POINTS: - [src/main/java/io/vertx/core/net/TrafficShapingOptions.java:33] should be fluent and return `TrafficShapingOptions` also missing javadoc. That is valid for other setters of this class.

### 38. wilkinsona — spring-projects/spring-boot#42443  (rubric=5, pts=1)
PR: PR #42443: Support service connections with RabbitMQ Streams and Testcontainers
REVIEW: POINTS: - [spring-boot-project/spring-boot-autoconfigure/src/main/java/org/springframework/boot/autoconfigure/amqp/RabbitStreamConnectionDetails.java:22] Upon further thought, I'm not sure that this will work for all cases. Those cases are: 1. One container to be used for both streams and "standard" messaging 2. Two containers: one for streams and one for standard messaging In the two container case, `RabbitContainerConnectionDetailsFactory` will match a container with the streams port exposed and I think we'll end up with a duplicate connection details failure. If we made `RabbitContainerConn

### 39. mickaelistria — eclipse-platform/eclipse.platform.swt#2513  (rubric=4, pts=1)
PR: PR #2513: StyledText#setLineVerticalIndent: fix overlapping code minings in edit
REVIEW: POINTS: - [bundles/org.eclipse.swt/Eclipse SWT Custom Widgets/common/org/eclipse/swt/custom/StyledText.java:9334] IIRC, this block of code can be very expensive. I see it's now going to be executed more often than usual. Instead of fully removing the guard, isn't there a way to refine it? However, I have not actually tried it on real big files. If you did so and are confident performance remains good, I'm fine with a merge, but code itself makes me unsure about it.

### 40. lhotari — apache/pulsar#25548  (rubric=5, pts=5)
PR: PR #25548: [improve][ml] Warn and emit metric when cursor ack state exceeds pers
REVIEW: SUMMARY: A few comments about details that Claude Code spotted. In addition 2 comments about the description: - reconcile the PR description (it claims broker‑level / no cardinality growth, but the code emits per‑cursor labels), - update the Modifications section to use the final metric names. Since the counter will only be emitted in Otel when the threshold has been crossed, it's fine to increase cardinality. In Prometheus this would be different. POINTS: - [managed-ledger/src/main/java/org/apache/bookkeeper/mledger/impl/OpenTelemetryManagedCursorStats.java:156] for attributes, pass `managedC

### 41. vietj — eclipse-vertx/vert.x#5120  (rubric=4, pts=1)
PR: PR #5120: Validate content length early during HttpServerResponse#sendFile
REVIEW: POINTS: - [src/test/java/io/vertx/core/http/HttpTest.java:2173] can you check this in the tests (hosts_config.txt is 23 bytes), someday we might modify hosts_config.txt and have this test not working correctly

### 42. laeubi — eclipse-tycho/tycho#5401  (rubric=5, pts=3)
PR: PR #5401: Migrate all @Component annotated classes to JSR330 annotations
REVIEW: POINTS: - [tycho-versions-plugin/src/main/java/org/eclipse/tycho/versions/engine/ProjectMetadataReader.java:37] @copilot according to https://eclipse.dev/sisu/org.eclipse.sisu.plexus/conversion-to-jsr330.html a component using `instantiationStrategy` should not use `@Singleton` but `@Named` - [tycho-versions-plugin/src/main/java/org/eclipse/tycho/versions/engine/VersionsEngine.java:38] @copilot `@Singleton` can not be used alone with maven sisu and requires and additional `@Named` ```suggestion @Singleton @Named ``` this is also missing on other places. - [tycho-versions-plugin/src/main/java/o

### 43. laeubi — eclipse-platform/eclipse.platform.swt#1045  (rubric=4, pts=0)
PR: PR #1045: Compile SWT natives for Windows on Arm64 (WoA).
REVIEW: SUMMARY: This module needs to be mentioned in https://github.com/eclipse-platform/eclipse.platform.swt/blob/master/binaries/pom.xml as well to be included in the build.

### 44. swankjesse — square/okhttp#8191  (rubric=4, pts=1)
PR: PR #8191: Allow constructor injection of MockWebServer
REVIEW: POINTS: - [android-test/build.gradle.kts:24] I think we should change our MockWebServer JUnit 5 extension API to use an annotation on each annotated class. It’s two imports instead of JUnit 4’s single import, but it’s self-contained in the test class.

### 45. laeubi — eclipse-platform/eclipse.platform.swt#67  (rubric=4, pts=1)
PR: PR #67: Let Display implement java.util.concurrent.Executor
REVIEW: POINTS: - [bundles/org.eclipse.swt/Eclipse SWT/gtk/org/eclipse/swt/widgets/Display.java:992] > You could add that concurrency framework thing to widget - and would solve two problems with a single call. This is not about calling a single method, I want to execute code in the UI thread and that's what executors are for, that the caller does not has to fiddle around what thread it is in, what display to acquire and so on. > You could add that concurrency framework thing to widget Having such API does not make sense at the widget level as it is not about calling a single widget method. > Please, 

### 46. vietj — eclipse-vertx/vert.x#2404  (rubric=4, pts=1)
PR: PR #2404: Fix bytesWritten when using Range headers
REVIEW: POINTS: - [src/test/java/io/vertx/test/core/HttpTest.java:1880] usually in java when you give the _length_, it means how many you want, otherwise _end_ is used, for instance in `java.lang.String`: ``` /* * @param length The number of bytes to decode */ public String(byte bytes[], int offset, int length, String charsetName); ``` we could modify the javadoc so it's clearer and use instead a similar sentence like _the number of bytes to send_

### 47. vietj — eclipse-vertx/vert.x#4441  (rubric=4, pts=1)
PR: PR #4441: Execute SSLHelper.validate as blocking
REVIEW: POINTS: - [src/main/java/io/vertx/core/net/impl/SSLHelper.java:521] the context should be provided as argument of the validate method instead of being access as a static.

### 48. beikov — hibernate/hibernate-orm#11583  (rubric=4, pts=1)
PR: PR #11583: HHH-20056 Cascade delete support detection in TiDB
REVIEW: POINTS: - [hibernate-community-dialects/src/main/java/org/hibernate/community/dialect/TiDBDialect.java:62] Yeah, you can use ```suggestion this.mySQLVersion = getVersion().isBefore( 7, 5 ) ? MINIMUM_MYSQL_VERSION : DatabaseVersion.make( 8, 0, 11 ); ```

### 49. HeikoKlare — eclipse-platform/eclipse.platform.swt#2531  (rubric=5, pts=1)
PR: PR #2531: GetLocation as Point.WithMonitor to ensure correct monitor association
REVIEW: POINTS: - [bundles/org.eclipse.swt/Eclipse SWT Tests/win32/org/eclipse/swt/widgets/CoordinateSystemMapperTests.java:228] Why do you need exactly 150% zoom and "specific coordinates"? If I understand correctly, the case to be tested is a gap in the coordinate system between a primary monitor (left) and a secondary monitor (right). `setupMonitors()` exactly produces such a situation. Even more appropriate than what I proposed would be to use instead of `1980` something like `monitor[1].getClientArea().width - OFFSET` with e.g. `OFFSET == 20` and as size something like `3 * OFFSET`. Then you are 

### 50. snuyanzin — Aiven-Open/klaw#702  (rubric=4, pts=1)
PR: PR #702: Filter requestors requests from the approval count
REVIEW: POINTS: - [core/src/main/java/io/aiven/klaw/helpers/db/rdbms/SelectDataJdbc.java:1454] why not to replace with count query? Count query is much faster since it doesn't need to load all the field values
