# Qwen suspected vs Claude suspected — full three-way content split

Suspected-vs-suspected (proven status is orthogonal, shown as a tag on Qwen items).


## OpenAPITools__openapi-generator  (Qwen 55 susp | Claude 3 | overlap 1 | Claude-only 2 | Qwen-only 54)

**Overlap (both suspected):**
- `DefaultCodegen#specVersionGreaterThanOrEqualTo310` — C: containsValue used instead of containsKey so x-original-swagger-version lookup is dead / Q: specVersionGreaterThanOrEqualTo310 always falls through: containsValue checks wrong thing

**Claude-only:**
- [med/hig] `InlineModelResolver#fixStringModel` — substring(1,0) StringIndexOutOfBounds on single-quote string example in unwrap branch
- [low/med] `InlineModelResolver#schemaContainsExample` — Uses != reference identity instead of !"".equals() so empty-example guard never fires

**Qwen-only:**
- (prov) StringUtils.java:189 — StringIndexOutOfBoundsException when camelize() is called with an empty string and LOWERCASE_FI
- (prov) ExamplesUtils.java:97 — NullPointerException when getAllExamples is called on an OpenAPI spec that has no components se
- (prov) ProcessUtils.java:198 — NullPointerException when hasOAuthMethods(List) or hasOpenIdConnectMethods(List) is called with
- (refu) SplitStringLambda.java:98 — IllegalFormatException when input contains percent characters like %s or %d, as String.format t
- (prov) Generate.java:199 — The --skip-validate-spec CLI option always disables spec validation even when set to false, bec
- (prov) DefaultCodegen.java:7056 — StackOverflowError when enum names like "a1", "a2", etc. exist alongside duplicates, since appe
- (prov) MergedSpecBuilder.java:82 — NullPointerException in buildMergedSpec when an OpenAPI spec has no paths defined, since result
- (prov) DefaultCodegen.java:4408 — StringIndexOutOfBoundsException when updateDefaultToEmptyContainer processes a rule consisting 
- (prov) SemVer.java:28 — NumberFormatException/NullPointerException in SemVer constructor when passed null or empty or n
- (prov) URLPathUtils.java:238 — NullPointerException in isRelativeUrl when server URL is null, since getUrl() can return null
- (prov) GeneratorSettings.java:327 — equals() and hashCode() in GeneratorSettings omit the serverVariables field, causing two object
- (prov) CaseFormatLambda.java:30 — CaseFormatLambda constructor has swapped/misleading parameter names where 'target' maps to init
- (prov) StringHelpers.java:52 — NullPointerException in StringHelpers.startsWith and endsWith when the input value is null, sin
- (prov) AccessAwareFieldValueResolver.java:24 — isUseSetAccessible called with FieldWrapper argument but the method expects AccessibleObject, c
- (prov) DoubleQuoteLambda.java:41 — NullPointerException in DoubleQuoteLambda when fragment.execute() returns null, since startsWit
- (prov) JoinWithCommaLambda.java:61 — NullPointerException in JoinWithCommaLambda when fragment.execute() returns null, since trim() 
- (prov) ZipUtil.java:74 — NullPointerException in ZipUtil.addFolderToZip when folder.listFiles() returns null (e.g., if d
- (prov) FirstLambda.java:48 — NullPointerException in FirstLambda when fragment.execute() returns null, since split is called
- (prov) SpringHttpStatusLambda.java:29 — NullPointerException in SpringHttpStatusLambda when fragment.execute() returns null, since the 
- (prov) TrimLambda.java:43 — NullPointerException in TrimLambda when fragment.execute() returns null, since trim() is called
- (prov) CamelCaseAndSanitizeLambda.java:73 — NullPointerException in CamelCaseAndSanitizeLambda when fragment.execute() returns null, since 
- (prov) LowercaseLambda.java:55 — NullPointerException in LowercaseLambda when fragment.execute() returns null, since toLowerCase
- (prov) UncamelizeLambda.java:48 — NullPointerException in UncamelizeLambda when fragment.execute() returns null, since trim() is 
- (prov) UniqueLambda.java:53 — NullPointerException in UniqueLambda when fragment.execute() returns null, since split() is cal
- (prov) TitlecaseLambda.java:85 — NullPointerException in TitlecaseLambda when fragment.execute() returns null and delimiter is n
- (prov) TrimLineBreaksLambda.java:45 — NullPointerException in TrimLineBreaksLambda when fragment.execute() returns null, since replac
- (prov) TrimTrailingWhiteSpaceLambda.java:47 — NullPointerException in TrimTrailingWhiteSpaceLambda when fragment.execute() returns null, sinc
- (prov) ForwardSlashLambda.java:41 — NullPointerException in ForwardSlashLambda when fragment.execute() returns null, since replace(
- (prov) BackSlashLambda.java:41 — NullPointerException in BackSlashLambda when fragment.execute() returns null, since replace() i
- (prov) SplitStringLambda.java:65 — NullPointerException in SplitStringLambda when fragment.execute() returns null, since length() 
- (prov) PrefixWithHashLambda.java:46 — NullPointerException in PrefixWithHashLambda when fragment.execute() returns null, since replac
- (prov) SnakecaseLambda.java:43 — NullPointerException in SnakecaseLambda when fragment.execute() returns null, since the result 
- (prov) KebabCaseLambda.java:42 — NullPointerException in KebabCaseLambda when fragment.execute() returns null, since replaceAll 
- (prov) GenApiService.java:84 — NullPointerException in GenApiService.downloadFile when fileId is not found in fileMap, since g
- (prov) CopyLambda.java:64 — NullPointerException in CopyLambda when fragment.execute() returns null, since startsWith/strip
- (prov) OptionalParameterLambda.java:54 — NullPointerException in OptionalParameterLambda when fragment.execute() returns null, since end
- (prov) PascalCaseLambda.java:47 — NullPointerException in PascalCaseLambda when fragment.execute() returns null, since the result
- (prov) ReplaceAllLambda.java:49 — NullPointerException in ReplaceAllLambda when fragment.execute() returns null, since replaceAll
- (refu) CaseFormatLambda.java:42 — NullPointerException in CaseFormatLambda when fragment.execute() returns null, since the result
- (prov) CamelCaseLambda.java:48 — NullPointerException in CamelCaseLambda when fragment.execute() returns null, since the result 
- (prov) RequiredParameterLambda.java:47 — NullPointerException in RequiredParameterLambda when fragment.execute() returns null, since end
- (prov) TrimWhitespaceLambda.java:46 — NullPointerException in TrimWhitespaceLambda when fragment.execute() returns null, since replac
- (refu) CodegenIgnoreProcessor.java:91 — NullPointerException in CodegenIgnoreProcessor.loadFromFile when targetIgnoreFile.getParentFile
- (prov) CodegenConfigLoader.java:37 — NullPointerException in CodegenConfigLoader.forName when a CodegenConfig implementation returns
- (prov) Validate.java:62 — NullPointerException in Validate.execute when SwaggerParseResult.getMessages() returns null, si
- (refu) HandlebarsEngineAdapter.java:118 — NullPointerException in HandlebarsEngineAdapter when a missing helper is used in non-section co
- (prov) InlineModelResolver.java:621 — NullPointerException in InlineModelResolver.flattenRequestBody when Components.getRequestBodies
- (prov) EscapeChar.java:53 — NullPointerException in EscapeChar when fragment.execute() returns null, since replaceAll is ca
- (prov) EscapeKeywordLambda.java:51 — NullPointerException in EscapeKeywordLambda when fragment.execute() returns null, since the nul
- (refu) GenerateBatch.java:128 — NullPointerException in GenerateBatch when the first config file has no parent directory (e.g.,
- (prov) StringUtils.java:73 — NullPointerException in StringUtils.underscore when word is null, since the Caffeine cache get 
- (prov) Generator.java:142 — NullPointerException in Generator.generate when CodegenConfig.openapiNormalizer() returns null,
- (prov) UppercaseLambda.java:44 — NullPointerException in UppercaseLambda when fragment.execute() returns null, since toUpperCase
- (refu) PythonStringUtils.java:47 — NullPointerException or JsonProcessingException in PythonStringUtils lambdas when fragment.exec

## Stirling-Tools__Stirling-PDF  (Qwen 24 susp | Claude 3 | overlap 0 | Claude-only 3 | Qwen-only 24)


**Claude-only:**
- [hig/hig] `GeneralUtils#handlePart` — Page token "-" makes rangeParts[0] throw AIOOBE, escaping the NumberFormatException-only catch
- [med/med] `GeneralUtils#handlePart` — Invalid 'n' token makes evaluateNFunc throw IllegalArgumentException, uncaught by parsePageList
- [low/hig] `ProcessExecutor#getInstance` — getInstance computeIfAbsent keyed on processType memoizes liveUpdates from first call only

**Qwen-only:**
- (refu) Base32Codec.java:85-91 — Base32 decoding produces incorrect output for inputs longer than ~6 characters because unmasked
- (refu) TotpService.java:92-94 — MessageDigest.isEqual() is used on UTF-8 byte arrays of potentially different-length strings. W
- (inco) ProcessExecutor.java:32 — ProcessExecutor uses default/zero semaphore limits and timeouts because it reads from a raw `ne
- (refu) ProcessExecutor.java:462 — Missing post-increment on the final insertIndex usage could lead to subtle bugs if the method i
- (refu) ProcessExecutor.java:476 — If a --host/--port/--host-location/--protocol flag appears at the very end of the command list 
- (prov) DatabaseService.java:383 — If a backup file exists with a name shorter than 11 characters (like "backup.sql"), deleteOldes
- (prov) SaasTeamService.java:55-61 — ensurePersonalTeam() can orphan a shared team by switching a user's team from their shared lead
- (prov) TempFileRegistry.java:143-149 — The age-based cleanup via getFilesOlderThan will never find temp directories or third-party tem
- (refu) GeneralUtils.java:35,47-59 — The @UtilityClass annotation conflicts with instance 'private final' fields. Either the fields 
- (prov) InProcessKeyValueCache.java:25-38 — TOCTOU race in get(): a concurrent put() can replace an expired entry with a fresh one between 
- (refu) DatabaseStorageProvider.java:47-52 — The existsById check before deleteById creates a TOCTOU race where a concurrent delete of the s
- (prov) DatabaseController.java:210 — Resource leak: the FileInputStream created by Files.newInputStream(filePath) is never closed af
- (prov) UIDataTessdataController.java:209-215 — Resource leak: FileInputStream from Files.newInputStream is passed to InputStreamResource which
- (prov) FileStorageService.java:227-231 — Storage leak: when replacing a file that had history/audit bundles with a new upload missing th
- (prov) SessionPersistentRegistry.java:161 — The cast to int on line 161 would overflow for durations exceeding ~68 years, but this is not p
- (prov) ProcessExecutor.java:304-305 — Potential hang: join() on reader threads has no timeout, so a stuck reader thread will block th
- (prov) TempFileManager.java:111-122 — Registry leak: when file.delete() fails, the file stays registered in TempFileRegistry and is n
- (prov) MfaService.java:166-184 — TOCTOU race in markTotpStepUsed(): concurrent TOTP requests with the same timeStep can both pas
- (inco) DatabaseService.java:472-491 — The ALLOWED_PATTERNS whitelist in validateSqlContent() is incomplete. Legitimate H2 backup SQL 
- (prov) GeneralUtils.java:527,59,594 — convertSizeToBytes JavaDoc claims PB (petabyte) support but PB is not actually supported. PB in
- (prov) JobQueue.java:243-268 — JobQueue.updateQueueCapacity() calls getQueueCapacity() (which locks queueLock) and then enters
- (prov) JobQueue.java:304-345 — In JobQueue.processQueue(), after removing a job from jobMap (line 344), if cancelJob is called
- (prov) JobQueue.java:466-482 — JobQueue.cancelJob() accesses shared mutable state (jobMap, jobQueue, currentQueueSize) without
- (refu) JobQueue.java:281-308 — ResourceMonitor.getCurrentStatus().get() is called inside synchronized(queueLock), holding the 

## alibaba__Sentinel  (Qwen 36 susp | Claude 3 | overlap 2 | Claude-only 1 | Qwen-only 34)

**Overlap (both suspected):**
- `AbstractRule#limitAppEquals` — C: limitAppEquals violates equals contract: ""/"default"/null inconsistency (transitivity) / Q: limitAppEquals() violates equals() contract with ""/null handling
- `RedisDataSource#initSslOptions` — C: OR guard enters block then derefs null keyFilePath.endsWith -> NPE; should be AND / Q: initSslOptions() NPE when keyCertChainFilePath set but keyFilePath is null

**Claude-only:**
- [low/med] `ParameterMetric#decreaseThreadCount` — putIfAbsent inserts spurious 0 entry never removed; orphaned map leak on decrement

**Qwen-only:**
- (inco) AbstractTokenBucket.java:76-78 — Race condition in token consumption: concurrent threads can both see enough tokens and decremen
- (prov) Context.java:115-117 — NPE when setCurNode is called before any entry is created in the context
- (refu) SimpleHttpHeartbeatSender.java:103-104 — HTTP 400 status code (Bad Request) will not be recognized as a client error, causing it to be s
- (prov) AuthorityRuleChecker.java:39-40 — Authority rule with limitApp containing whitespace-separated entries like "app1, app2" will fai
- (prov) DefaultCircuitBreakerRuleManager.java:83-89 — Race condition in getDefaultCircuitBreakers: concurrent calls can create duplicate CircuitBreak
- (prov) RequestLimiter.java:81-87 — Race condition in RequestLimiter.tryPass() allows multiple concurrent threads to pass the QPS c
- (prov) FlowRuleChecker.java:194-197 — InterruptedException in applyTokenResult is swallowed and only printed to stderr instead of usi
- (prov) NettyConnection.java:42 — NPE when channel remote address is an unresolved InetSocketAddress - socketAddress.getAddress()
- (prov) WarmUpController.java:114-115 — WarmUpController.canPass() does not check for null node before calling node.passQps(), which wo
- (prov) WarmUpRateLimiterController.java:79-83 — InterruptedException in WarmUpRateLimiterController canPass is silently swallowed in empty catc
- (prov) NettyTransportServer.java:158-161 — NPE when closeConnection is called for a client address that is not in the connection pool - ge
- (prov) SystemStatusListener.java:70-73 — Division by zero in SystemStatusListener.run() when processUpTimeDiffInMs is 0, producing Infin
- (prov) DegradeSlot.java:62 — DegradeSlot.exit() could NPE if context is null since context.getCurEntry() is called without n
- (prov) RuleManager.java:103 — regexCacheRules can be set to Collections.emptyMap() by setRules() in another thread, causing U
- (prov) RuleManager.java:128-130 — getOriginalRules() returns internal map reference allowing direct mutation of internal state, c
- (prov) RuleManager.java:33-35 — Non-volatile fields regexRules, simpleRules, regexCacheRules in RuleManager cause visibility is
- (inco) ConcurrentClusterFlowChecker.java:97-98 — NPE in ConcurrentClusterFlowChecker.releaseConcurrentToken() when CurrentConcurrencyManager.get
- (prov) WarmUpRateLimiterController.java:71-72 — WarmUpRateLimiterController.waitTime calculation is wrong because addAndGet returns the OLD val
- (prov) ParameterMetric.java:207-212 — TOCTOU race in ParameterMetric.addThreadCount: putIfAbsent+put pattern causes thread count corr
- (prov) DefaultClusterTokenClient.java:186-188 — DefaultClusterTokenClient.requestConcurrentToken returns null instead of TokenResult, causing N
- (inco) NettyTransportClient.java:184-190 — NettyTransportClient.stop() busy-wait loop can block forever if client is stuck in PENDING stat
- (prov) HttpHeartbeatSender.java:99-102 — HttpHeartbeatSender reads status code AFTER closing response, and response.close() is not in fi
- (prov) WarmUpController.java:140-157 — WarmUpController.syncToken has non-atomic CAS+addAndGet sequence that can cause incorrect token
- (refu) AbstractSentinelAspectSupport.java:112-124 — handleDefaultFallback at line 118 doesn't handle the case where defaultFallback method has been
- (inco) RegularExpireStrategy.java:118 — RegularExpireStrategy.clearToken NPE when ClusterFlowRuleManager.getFlowRuleById returns null f
- (prov) GatewayParamParser.java:72-78 — GatewayParamParser.parseParameterFor can throw ArrayIndexOutOfBoundsException when paramItem.ge
- (prov) SimpleHttpHeartbeatSender.java:92-101 — SimpleHttpHeartbeatSender.currentAddressIdx is never incremented, so heartbeat always goes to t
- (prov) SentinelWebInterceptor.java:42-49 — SentinelWebInterceptor constructor calls super(config) before null check, so null config always
- (prov) RedisDataSource.java:259-270 — RedisDataSource.readSource() creates a new connection on each call but never closes it, causing
- (refu) NettyTransportClient.java:114-134 — NettyTransportClient cannot reconnect after first failed connection because currentState CAS ne
- (prov) ZookeeperDataSource.java:171-180 — ZookeeperDataSource.close() incorrectly closes the shared CuratorFramework, breaking other Zook
- (prov) AbstractCircuitBreaker.java:69-79 — AbstractCircuitBreaker.tryPass() has TOCTOU race: state check between CLOSED and OPEN can miss 
- (refu) ParamFlowChecker.java:112-118 — ParamFlowChecker.passSingleValueCheck thread count local increment never persisted
- (prov) GlobalRequestLimiter.java:32-37 — GlobalRequestLimiter.initIfAbsent race condition creating duplicate RequestLimiter instances

## alibaba__arthas  (Qwen 20 susp | Claude 3 | overlap 2 | Claude-only 1 | Qwen-only 18)

**Overlap (both suspected):**
- `GroupMatcher.And#add` — C: And(Matcher...) uses fixed-size Arrays.asList so add() throws UnsupportedOperationException / Q: add() on GroupMatcher.And throws UnsupportedOperationException; Arrays.asList unmodifiable
- `TunnelSocketFrameHandler#channelRead0` — C: findProxyRequestPromise can return null (60s timeout removal); promise deref causes NPE / Q: NPE when findProxyRequestPromise returns null; promise.setSuccess/setFailure throws NPE

**Claude-only:**
- [med/hig] `GroupMatcher.Or#add` — Or(Matcher...) varargs ctor uses Arrays.asList so add() throws UnsupportedOperationException

**Qwen-only:**
- (prov) IPUtils.java:31-68 — getLocalIP() may return a loopback address or an unsuitable IP when no valid non-loopback site-
- (inco) ThreadUnsafeFixGaStack.java:23-28 — ThreadUnsafeFixGaStack allows pushing one element too many, causing ArrayIndexOutOfBoundsExcept
- (refu) WildcardMatcher.java:67-102 — WildcardMatcher.match() throws StringIndexOutOfBoundsException when the pattern ends with a lon
- (refu) ProcessUtils.java:416-426 — findJps() throws NullPointerException when JAVA_HOME environment variable is not set and jps bi
- (prov) AdviceListenerManager.java:106-107 — Key collisions in AdviceListenerManager can cause wrong advice listeners to be queried or regis
- (prov) ProcessImpl.java:477-496 — StatisticsFunction results in ProcessOutput.close() are computed but never written to the termi
- (refu) DynamicCompiler.java:53-57 — DynamicJavaFileManager and StandardJavaFileManager are never closed, potentially leaking file d
- (inco) ObjectService.java:105 — Wrong variable logged in error message - should log 'resultExpress' instead of 'express' when r
- (prov) TunnelServer.java:231-238 — NullPointerException when setPath(null) is called since path.trim() is invoked without null che
- (refu) DirectoryBrowser.java:157 — When dir.getParent() returns null, new File(null, path) creates an invalid File object that won
- (prov) GrpcDispatcher.java:33 — Using non-thread-safe HashMap for static maps accessed from multiple gRPC handler threads can c
- (prov) GrepHandler.java:49-56 — Race condition in GrepHandler.inject() where static cli field is checked and assigned without s
- (prov) AccessPoint.java:4 — Typo ACCESS_AFTER_RETUNING (should be ACCESS_AFTER_RETURNING) in AccessPoint enum, any reflecti
- (prov) HttpApiHandler.java:210 — NullPointerException in catch block when session.getResultDistributor() returns null, unlike th
- (prov) RateCounter.java:57-71 — RateCounter.rate() returns NaN when no values have been updated because it divides by countLeng
- (prov) FieldUtils.java:213-217 — getField(Class, String) can return null when no matching field exists, but the javadoc does not
- (prov) ProcessUtils.java:261-263 — If getCause() returns null, the variable e becomes null, causing NPE in the else branch when e.
- (prov) MonitorAdviceListener.java:251-253 — Key.hashCode() uses commutative addition causing excessive hash collisions in ConcurrentHashMap

## alibaba__druid  (Qwen 24 susp | Claude 3 | overlap 0 | Claude-only 3 | Qwen-only 24)


**Claude-only:**
- [hig/hig] `DbType#oceanbase_oracle` — oceanbase_oracle uses int 1<<31 which sign-extends to fill high 33 bits of long mask
- [low/hig] `WallVisitorUtils#form` — form(String) throws StringIndexOutOfBounds on length-1 name equal to the quote char
- [low/med] `StringUtils#removeNameQuotes` — removeNameQuotes returns null for length<=1 input, dropping valid single-char names

**Qwen-only:**
- (prov) LRUCache.java:26 — LRUCache does not implement true LRU eviction because accessOrder is set to false, causing it t
- (prov) ConcurrentLruCache.java:340-341 — In ConcurrentLruCache.clear(), the readCount array is not reset to zero, causing stale buffer i
- (refu) DruidXADataSource.java:43-50 — Connection leak in DruidXADataSource.getXAConnection(): the DruidPooledConnection obtained via 
- (prov) RandomDataSourceSelector.java:234-240 — RandomDataSourceSelector.getRandomDataSource() can throw IndexOutOfBoundsException or return wr
- (prov) JtdsXAResource.java:88-94 — JtdsXAResource.isSameRM() throws NullPointerException when either this.rmHost or xares.rmHost i
- (prov) ConcurrentLruCache.java:129-142 — ConcurrentLruCache.clear() can cause currentSize to be decremented twice for nodes that have pe
- (inco) ConnectionProxyImpl.java:75-84 — ConnectionProxyImpl.createChain() can return the same FilterChainImpl to multiple threads simul
- (prov) EncodingConvertFilter.java:197-208 — EncodingConvertFilter leaks Reader resources in clob_getCharacterStream and callableStatement_s
- (prov) Utils.java:30-37 — Utils.read(InputStream in) does not close the InputStream after reading, and Utils.read(Reader)
- (prov) DruidDataSource.java:2121-2123 — DruidConnectionHolder.getStatementPool() has a race condition in its lazy initialization that c
- (prov) WallVisitorUtils.java:141 — WallVisitorUtils.check(SQLDropTableStatement) throws ClassCastException when the table source e
- (prov) DbType.java:44-47 — DbType.antspark and DbType.spark share the same bit value (1 << 30), so any bitwise operation c
- (prov) WallConfig.java:131 — WallConfig.updateCheckColumns uses non-thread-safe HashMap, which can cause ConcurrentModificat
- (prov) WrapperProxyImpl.java:94-106 — WrapperProxyImpl has a race condition in the lazy initialization of 'attributes' where concurre
- (prov) StringUtils.java:333-335 — StringUtils.isNumber(char[]) returns true for input '.' (single period) while StringUtils.isNum
- (prov) WallConfig.java:296-298 — WallConfig.loadConfig(String dir) throws NullPointerException when dir is null because it calls
- (inco) MapComparator.java:37 — MapComparator.compare(Number, Number) uses subtraction-and-cast for numeric comparison which ov
- (prov) DruidDataSourceStatManager.java:209-212 — DruidDataSourceStatManager.getDruidDataSourceInstances() has a TOCTOU race: it calls getInstanc
- (prov) DruidDataSourceWrapper.java:55-57 — DruidDataSourceWrapper.autoAddFilters() can add null elements to the filters list if Spring inj
- (prov) IPAddress.java:86-112 — IPAddress.isClassA(), isClassB(), isClassC() check the wrong bits (LSB instead of MSB of the fi
- (prov) ConcurrentLruCache.java:278-282 — ConcurrentLruCache.ReadOperations.detectNumberOfBuffers() returns 1 when availableProcessors is
- (prov) WebAppStatManager.java:51-61 — WebAppStatManager.getWebAppStatSet() has a broken lazy initialization: webAppStatSet field is n
- (prov) WebAppStat.java:151-161 — WebAppStat.reset() uses sessionStatLock.readLock() for write operations (resetting entries and 
- (prov) DruidStatService.java:252-258 — DruidStatService.comparatorOrderBy() does not validate user-controlled pagination parameters (p

## alibaba__easyexcel  (Qwen 96 susp | Claude 4 | overlap 3 | Claude-only 1 | Qwen-only 93)

**Overlap (both suspected):**
- `CsvRow#getCell(int)` — C: getCell guards cellnum>=size but returns cellList.get(cellnum-1): off-by-one, get(0) throws / Q: getCell(0) throws IndexOutOfBoundsException due to off-by-one accessing cellList.get(-1)
- `CsvRow#getPhysicalNumberOfCells()` — C: getPhysicalNumberOfCells returns getRowNum() (row index) instead of cellList.size() / Q: getPhysicalNumberOfCells returns the row index instead of number of cells
- `NumberDataFormatterUtils#format` — C: ThreadLocal DataFormatter set on first call; later calls ignore differing 1904/locale/scientifi / Q: ThreadLocal-cached DataFormatter ignores differing parameters on subsequent calls, stale config

**Claude-only:**
- [low/hig] `BigDecimalBooleanConverter#convertToExcelData` — convertToExcelData uses scale-sensitive BigDecimal.ONE.equals; 1.0 (scale 1) written as false

**Qwen-only:**
- (prov) FileUtils.java:77 — Files larger than 2GB will cause integer overflow, leading to wrong byte array size or IOExcept
- (pend) FileUtils.java:56-64 — POI temporary files may fail to be created because the poiFilesPath directory doesn't exist
- (pend) LoopMergeStrategy.java:33 — Misleading error message that says parameter must be > 1 when it actually accepts >= 1
- (prov) BooleanUtils.java:31 — Silently returns FALSE for null string instead of propagating the null, which could mask bugs
- (pend) IoUtils.java:34 — Misleading dead code that wastes CPU cycles generating a byte array that is immediately discard
- (prov) BooleanNumberConverter.java:40 — Passing null Boolean will throw NullPointerException due to auto-unboxing in `if (value)`
- (prov) SheetUtils.java:51-53 — NPE when readSheet.getSheetName() returns null and autoTrim is true
- (prov) CsvSheet.java:149-151 — getPhysicalNumberOfRows() returns wrong count - it returns the number of flushed rows, not the 
- (pend) LongestMatchColumnWidthStyleStrategy.java:55 — NPE when getStringCellValue() or getStringValue() returns null
- (pend) WriteWorkbookHolder.java:259-266 — If autoCloseStream is false but the templateInputStream was intended to be reused after this, i
- (prov) AbstractExcelWriteExecutor.java:92 — NPE when writing NUMBER cell data with null numberValue
- (prov) StyleUtil.java:187 — ClassCastException when originFont is XSSFFont but workbook creates HSSFFont due to mismatched 
- (pend) DefaultAnalysisEventProcessor.java:148 — Dead code: the null check on stringEntry will never trigger as Map.entrySet() iteration never p
- (pend) WorkBookUtil.java:69 — CSV writing silently fails if OutputStream throws IOException because PrintWriter suppresses ex
- (pend) OnceAbsoluteMergeStrategy.java:34-35 — Misleading error message: says parameters must be > 0 but the check accepts >= 0
- (pend) CsvRow.java:110-114 — getLastCellNum() returns size instead of size-1, inconsistent with POI contract where last cell
- (pend) LoopMergeStrategy.java:39-41 — Dead code: the check at line 39 for columnExtend==1 && eachRow==1 is unreachable because the va
- (pend) LoopMergeStrategy.java:42-43 — Misleading error message says columnIndex must be > 0 but 0 is accepted by the check
- (pend) DataFormatter.java:181-185 — useScientificFormat is never properly initialized because the null check is on use1904windowing
- (prov) CsvSheet.java:673-674 — NPE when booleanValue field is null in CSV BOOLEAN cell value formatting
- (prov) BooleanNumberConverter.java:31 — NPE when getNumberValue() returns null in BooleanNumberConverter
- (prov) LongestMatchColumnWidthStyleStrategy.java:34 — NPE when isHead is null due to auto-unboxing in boolean || expression
- (prov) NumberUtils.java:61 — NPE when num is null in NumberUtils.formatToCellData() and format()
- (prov) NumberUtils.java:36-38 — IllegalArgumentException when roundingMode is null in NumberUtils.format()
- (prov) BooleanStringConverter.java:36 — NPE when value is null in BooleanStringConverter.convertToExcelData()
- (prov) LocalDateTimeNumberConverter.java:37 — NPE when cellData.getNumberValue() returns null in LocalDateTimeNumberConverter.convertToJavaDa
- (prov) LocalDateTimeNumberConverter.java:46-54 — NPE when value is null in LocalDateTimeNumberConverter.convertToExcelData()
- (prov) StringNumberConverter.java:40 — NPE when cellData.getNumberValue() returns null in StringNumberConverter.convertToJavaData()
- (pend) LocalDateTimeStringConverter.java:34 — NPE when cellData.getStringValue() returns null in LocalDateTimeStringConverter.convertToJavaDa
- (prov) LocalDateTimeStringConverter.java:45 — NPE when value is null in LocalDateTimeStringConverter.convertToExcelData()
- (prov) LocalDateNumberConverter.java:38 — NPE when cellData.getNumberValue() returns null in LocalDateNumberConverter.convertToJavaData()
- (prov) LocalDateNumberConverter.java:50 — NPE when value is null in LocalDateNumberConverter.convertToExcelData()
- (prov) LocalDateStringConverter.java:45 — NPE when value is null in LocalDateStringConverter.convertToExcelData()
- (pend) LocalDateStringConverter.java:34 — NPE when cellData.getStringValue() returns null in LocalDateStringConverter.convertToJavaData()
- (prov) IntegerNumberConverter.java:32 — NPE when cellData.getNumberValue() returns null in IntegerNumberConverter.convertToJavaData()
- (pend) IntegerStringConverter.java:33 — NPE when cellData.getStringValue() returns null in IntegerStringConverter.convertToJavaData()
- (prov) LongNumberConverter.java:32 — NPE when cellData.getNumberValue() returns null in LongNumberConverter.convertToJavaData()
- (prov) DoubleNumberConverter.java:31 — NPE when cellData.getNumberValue() returns null in DoubleNumberConverter.convertToJavaData()
- (prov) FloatNumberConverter.java:32 — NPE when cellData.getNumberValue() returns null in FloatNumberConverter.convertToJavaData()
- (prov) BigIntegerNumberConverter.java:33 — NPE when cellData.getNumberValue() returns null in BigIntegerNumberConverter.convertToJavaData(
- (prov) StringBooleanConverter.java:30 — NPE when cellData.getBooleanValue() returns null in StringBooleanConverter.convertToJavaData()
- (prov) DateNumberConverter.java:37 — NPE when cellData.getNumberValue() returns null in DateNumberConverter.convertToJavaData()
- (prov) DateNumberConverter.java:49 — NPE when value is null in DateNumberConverter.convertToExcelData()
- (pend) DateStringConverter.java:34 — NPE when cellData.getStringValue() returns null in DateStringConverter.convertToJavaData()
- (pend) DateStringConverter.java:45 — NPE when value is null in DateStringConverter.convertToExcelData()
- (prov) DefaultAnalysisEventProcessor.java:141 — NPE when headData.getForceIndex() or headData.getForceName() is null due to auto-unboxing
- (prov) DateUtils.java:168 — NPE when dateString is null in DateUtils.switchDateFormat()
- (prov) MapCache.java:29 — IndexOutOfBoundsException when key >= cache.size() in MapCache.get()
- (prov) CellDataTypeEnum.java:70 — buildFromCellType() returns null for unknown cell types, causing NPE in downstream code
- (pend) LocalDateDateConverter.java:28 — IllegalArgumentException when value is null in LocalDateDateConverter.convertToExcelData() beca
- (pend) DateDateConverter.java:26 — IllegalArgumentException when value is null in DateDateConverter.convertToExcelData() because W
- (pend) LongStringConverter.java:33 — NPE when cellData.getStringValue() returns null in LongStringConverter.convertToJavaData()
- (pend) FloatStringConverter.java:33 — NPE when cellData.getStringValue() returns null in FloatStringConverter.convertToJavaData()
- (pend) DoubleStringConverter.java:33 — NPE when cellData.getStringValue() returns null in DoubleStringConverter.convertToJavaData()
- (pend) ByteStringConverter.java:33 — NPE when cellData.getStringValue() returns null in ByteStringConverter.convertToJavaData()
- (prov) LongestMatchColumnWidthStyleStrategy.java:66 — NPE when cellData.getBooleanValue() or getNumberValue() returns null in LongestMatchColumnWidth
- (pend) WriteContextImpl.java:366 — Resource leak: tempFileOutputStream not closed if workbook.close() throws in finally block
- (prov) LabelRecordHandler.java:21 — NPE when getAutoTrim() returns null (auto-unboxing), and IllegalArgumentException when lrec.get
- (pend) BuiltinFormats.java:525 — Null keys put into BUILTIN_FORMATS_MAP_CN and BUILTIN_FORMATS_MAP_US HashMaps, causing incorrec
- (pend) CellTagHandler.java:49 — NumberFormatException when cell style attribute (s) contains non-numeric value in CellTagHandle
- (pend) WriteSheetHolder.java:114 — NPE when sheet or cachedSheet is null in WriteSheetHolder.getNewRowIndexAndStartDoWrite()
- (prov) LabelSstRecordHandler.java:36 — NPE when getAutoTrim() returns null (auto-unboxing) in LabelSstRecordHandler.processRecord()
- (prov) DefaultAnalysisEventProcessor.java:156 — NPE when getAutoTrim() returns null (auto-unboxing) in DefaultAnalysisEventProcessor.buildHead(
- (prov) IntegerBooleanConverter.java:32 — NPE when cellData.getBooleanValue() returns null in IntegerBooleanConverter.convertToJavaData()
- (prov) BofRecordHandler.java:71 — NPE when getNeedReadSheet() returns null (auto-unboxing) in BofRecordHandler.initReadSheetDataL
- (prov) ShortBooleanConverter.java:32 — NPE when cellData.getBooleanValue() returns null in ShortBooleanConverter.convertToJavaData()
- (prov) LongBooleanConverter.java:32 — NPE when cellData.getBooleanValue() returns null in LongBooleanConverter.convertToJavaData()
- (prov) FloatBooleanConverter.java:32 — NPE when cellData.getBooleanValue() returns null in FloatBooleanConverter.convertToJavaData()
- (prov) DoubleBooleanConverter.java:32 — NPE when cellData.getBooleanValue() returns null in DoubleBooleanConverter.convertToJavaData()
- (prov) BigIntegerBooleanConverter.java:32 — NPE when cellData.getBooleanValue() returns null in BigIntegerBooleanConverter.convertToJavaDat
- (pend) XlsxSaxAnalyser.java:287 — NPE when cellComment.getString() returns null in XlsxSaxAnalyser.readComments()
- (prov) XlsxSaxAnalyser.java:240 — inputStream closed twice in parseXmlSource - once in try and again in finally
- (prov) Ehcache.java:147 — NPE when fileCache.get(route) returns null in Ehcache.get() - dataList is null
- (pend) DateUtils.java:125 — NPE or DateTimeParseException when dateString is null in DateUtils.parseLocalDateTime()
- (prov) CsvWorkbook.java:230 — NPE when csvCellStyleList is null in CsvWorkbook.getNumCellStyles()
- (prov) CountTagHandler.java:19 — NPE or incorrect parsing when dimension ref attribute is null or missing ':' in CountTagHandler
- (prov) BigDecimalBooleanConverter.java:32 — NPE when cellData.getBooleanValue() is null (auto-unboxing) in BigDecimalBooleanConverter.conve
- (pend) CellFormulaTagHandler.java:27 — NPE when getTempCellData() returns null in CellFormulaTagHandler.endElement()
- (prov) CsvExcelReadExecutor.java:122 — NPE when getAutoTrim() returns null (auto-unboxing in ternary) in CsvExcelReadExecutor.dealReco
- (prov) DefaultWriteHandlerLoader.java:39 — NPE when useDefaultStyle is null (auto-unboxing in if condition) in DefaultWriteHandlerLoader.l
- (pend) CellExtra.java:43 — NPE when range parameter is null in CellExtra constructor
- (prov) CellTagHandler.java:101 — NPE when getAutoTrim() returns null (auto-unboxing in && condition) in CellTagHandler.endElemen
- (prov) SheetUtils.java:49 — NPE when getGlobalConfiguration().getAutoTrim() is null (auto-unboxing in || condition) in Shee
- (prov) DefaultAnalysisEventProcessor.java:46 — NPE when getIgnoreEmptyRow() returns null (auto-unboxing in if condition) in DefaultAnalysisEve
- (prov) StringNumberConverter.java:63 — NumberFormatException when value is null in StringNumberConverter.convertToExcelData()
- (pend) DimensionWorkbookWriteHandler.java:77 — NPE when ctWorksheet.getDimension() is null in DimensionWorkbookWriteHandler.afterWorkbookDispo
- (prov) AbstractHolder.java:109 — NPE when newInitialization is null (auto-unboxing in isNew()) in AbstractHolder - occurs when n
- (pend) StyleUtil.java:264-265 — NPE when currentCoordinate is null (auto-unboxing) in StyleUtil.getCellCoordinate()
- (prov) EofRecordHandler.java:41 — NPE when getRowIndex() is null (auto-unboxing in arithmetic) in EofRecordHandler.processRecord(
- (pend) LoopMergeStrategy.java:60 — NPE when context.getRowIndex() is null (auto-unboxing) in LoopMergeStrategy.afterRowDispose()
- (prov) AbstractMergeStrategy.java:19 — NPE when context.getHead() is null (auto-unboxing) in AbstractMergeStrategy.afterCellDispose()
- (pend) AbstractCellStyleStrategy.java:27 — NPE when context.getHead() is null (auto-unboxing) in AbstractCellStyleStrategy.afterCellDispos
- (pend) AbstractRowHeightStyleStrategy.java:19 — NPE when context.getHead() is null (auto-unboxing) in AbstractRowHeightStyleStrategy.afterRowCr

## alibaba__nacos  (Qwen 51 susp | Claude 5 | overlap 3 | Claude-only 2 | Qwen-only 48)

**Overlap (both suspected):**
- `PageUtil#subPage` — C: pagesAvailable = totalCount/pageSize + 1 over-reports one page when evenly divisible / Q: pagesAvailable wrong when totalCount exactly divisible by pageSize, reports one extra page
- `LocalFileMeta#get` — C: append stores Object via put but get uses Properties.getProperty, dropping non-String values / Q: non-String values stored via append cannot be retrieved via get, silent data loss
- `StringUtils#join` — C: trailing null element leaves a dangling separator in join output / Q: join produces trailing separators when null elements are at the end of the collection

**Claude-only:**
- [low/med] `IoUtils#copy(InputStream,OutputStream)` — copy accumulates size in int though return is long, overflowing on >2GB streams
- [low/med] `GroupKey2#parseKey` — trailing '%' escape triggers charAt(++i) OOB, throwing SIOOBE not IllegalArgumentException

**Qwen-only:**
- (prov) NotifyCenter.java:384 — Calling publisher.shutdown() on a null reference when deregisterPublisher is called for an even
- (refu) HessianSerializer.java:61 — Calling non-existent String.format() instance method instead of static String.format() will cau
- (prov) LocalDataSourceServiceImpl.java:143 — DriverManager.getConnection is called for Derby shutdown but the resulting Connection is never 
- (prov) InstanceUtil.java:63 — ClassCastException when instance metadata contains non-Boolean or non-Double values for PUBLISH
- (prov) ReflectUtils.java:80-87 — getField() will fail on private fields because it doesn't set accessible=true, unlike the simil
- (refu) NotifyCenter.java:147 — NullPointerException in shutdown() when sharePublisher is null due to failed initialization in 
- (prov) NotifyCenter.java:251 — NoSuchElementException thrown in deregisterSubscriber() even when the caller just wants to dere
- (prov) RandomUtils.java:50 — nextLong may return a value >= endExclusive for large ranges due to double precision loss in th
- (prov) InternetAddressUtil.java:141 — splitIpPortStr may return incorrect results for edge cases: trailing colon (e.g., "192.168.1.1:
- (prov) ProtoMessageUtil.java:52 — parse() throws NPE/AIOOBE when called with null or empty byte array, instead of returning meani
- (prov) RegexParser.java:50-56 — regexFormat produces incorrect regex output when '?' characters are followed by non-'?' charact
- (prov) Chooser.java:118-137 — Chooser.Ref.items list is never cleared between refresh() calls, causing items to accumulate an
- (prov) IoUtils.java:90-102 — tryCompress returns potentially incomplete/corrupted compressed data when an exception occurs d
- (inco) ConnectionManager.java:301-303 — ArrayIndexOutOfBoundsException when redirectAddress doesn't contain a colon or contains multipl
- (prov) GenericPoller.java:40 — GenericPoller.next() throws ArithmeticException (division by zero) when called on an empty item
- (prov) ExceptionUtil.java:45-47 — Infinite loop in getAllExceptionMsg if exception cause chain contains a circular reference.
- (prov) NamingUtils.java:87-89 — parseServiceKey throws NPE for null input, and returns unexpected array size when service key c
- (prov) FuzzyGroupKeyPattern.java:109 — matchPattern and getNamespaceFromPattern throw ArrayIndexOutOfBoundsException when groupKeyPatt
- (prov) ConvertUtils.java:81 — toLong(Object val) throws NullPointerException when val is null, despite being expected to hand
- (prov) DateFormatUtils.java:65 — DateFormatUtils.format creates new SimpleDateFormat without timezone, leading to inconsistent d
- (inco) AccumulateStatCount.java:41-44 — AccumulateStatCount.stat() has data race on non-volatile lastStatValue leading to incorrect acc
- (prov) GrpcBiStreamRequestAcceptor.java:87-121 — GrpcBiStreamRequestAcceptor uses empty clientIp for tracing in onError/onCompleted callbacks, m
- (prov) ReentrantAtomicLock.java:53 — ReentrantAtomicLock.doTryLock() throws NPE when lockInfo.getOwner() is null and the lock is alr
- (prov) FailoverReactor.java:127 — FailoverReactor.serviceMap is reassigned in a scheduled thread without volatile or synchronizat
- (prov) NamingUtils.java:98 — NamingUtils.getServiceName() throws ArrayIndexOutOfBoundsException when input ends with '@@' si
- (prov) InetUtils.java:112 — InetUtils.refreshIp() throws NPE when findFirstNonLoopbackAddress() returns null, as Objects.re
- (prov) BatchTaskCounter.java:51-55 — BatchTaskCounter.batchSuccess() throws IndexOutOfBoundsException when batch is 0 or negative, s
- (refu) CollectionUtils.java:307-317 — CollectionUtils.getOnlyElement() throws NoSuchElementException from iterator.next() when iterab
- (prov) Service.java:115 — Service.equals() throws NPE when namespace, group, or name is null, since it calls .equals() on
- (prov) SimpleFlowData.java:35-78 — SimpleFlowData has data races on non-volatile int fields `index` and `average`, causing concurr
- (inco) BaseDatabaseOperate.java:248-254 — BaseDatabaseOperate.update() commits transactions that should roll back when BadSqlGrammarExcep
- (prov) ThreadPoolManager.java:79-85 — ThreadPoolManager.register() creates a non-thread-safe HashMap as the inner map, which can caus
- (prov) ConnectionManager.java:293-318 — ConnectionManager.loadSingle() always returns true even when connection is null or not SDK sour
- (prov) GroupKey2.java:51-94 — GroupKey2.parseKey() misinterprets the last segment when group is empty, assigning tenant conte
- (prov) ServiceUtil.java:272 — ServiceUtil.selectInstancesWithHealthyProtection() divides by allInstances.size() without check
- (prov) ExpressionInterpreter.java:84,98 — ExpressionInterpreter.parseExpression() calls split(PROVIDER_PREFIX)[1] without checking array 
- (prov) ServiceInfoUpdateService.java:55 — ServiceInfoUpdateService.futureMap is a non-thread-safe HashMap accessed concurrently from mult
- (prov) ServiceInfoDiskCacheRefresher.java:122-133 — ServiceInfoDiskCacheRefresher.flushPendingEvents() iterates keySet() and does separate get() + 
- (prov) DiskCache.java:77-78 — DiskCache uses Charset.defaultCharset() for writing and reading cache files instead of a fixed 
- (prov) SimpleReadWriteLock.java:47-53 — SimpleReadWriteLock.releaseReadLock() doesn't guard against being called while write-locked, co
- (prov) JacksonUtils.java:46 — JacksonUtils.registerSubtype() modifies the shared static ObjectMapper concurrently without syn
- (prov) DefaultRequestFuture.java:247-258 — DefaultRequestFuture.cancel() calls notifyAll() without setting isDone = true, causing waiting 
- (prov) Instance.java:226-238 — Instance.equals/hashCode based on toString() with HashMap metadata can violate the equals/hashC
- (prov) ConfigRocksDbDiskService.java:54 — ConfigRocksDbDiskService.rocksDbMap is a non-thread-safe HashMap accessed concurrently by multi
- (prov) ClientTrackService.java:122-123 — ClientTrackService.refreshClientRecord() replaces the volatile clientRecords map with a new emp
- (prov) RequestHandlerRegistry.java:47-49 — RequestHandlerRegistry.registryHandlers and sourceRegistry are non-thread-safe HashMaps accesse
- (prov) WebUtils.java:103-111 — WebUtils.resolveValue() re-encodes UTF-8 bytes to target encoding instead of properly decoding 
- (prov) FailoverReactor.java:56 — failoverSwitchEnable is reassigned in a scheduled thread without volatile or synchronization, c

## apache__commons-collections  (Qwen 20 susp | Claude 2 | overlap 1 | Claude-only 1 | Qwen-only 19)

**Overlap (both suspected):**
- `OrderedProperties#merge` — C: merge() leaves stale key in orderedKeys when remapping returns null (mapping removed) / Q: merge() adds keys to orderedKeys unconditionally; null remap result leaves stale key

**Claude-only:**
- [med/hig] `OrderedProperties#compute` — compute() never removes key from orderedKeys when remapping returns null, leaving stale key

**Qwen-only:**
- (prov) StaticBucketMap.java:170-171 — Passing a non-Map.Entry object to EntrySet.contains() throws ClassCastException instead of retu
- (inco) StringKeyAnalyzer.java:141 — isPrefix() extracts wrong substring when offsetInBits is non-zero, causing incorrect prefix mat
- (refu) UnmodifiableList.java:83-85 — The add(Object) method doesn't properly override Collection.add(E) due to the wrong parameter t
- (refu) CompositeSet.java:467-468 — CompositeSet.toArray(T[]) violates the Collection contract: when the passed array is larger tha
- (inco) CartesianProductIterator.java:117-119 — CartesianProductIterator.hasNext() returns true after all tuples have been generated when inner
- (prov) DualTreeBidiMap.java:373-374 — DualTreeBidiMap.nextKey(K key) throws NoSuchElementException when all keys are less than the gi
- (prov) Flat3Map.java:148-157 — Flat3Map.EntrySet.remove(Object) incorrectly removes entries based on key alone without verifyi
- (refu) LazyIteratorChain.java:127-131 — LazyIteratorChain.remove() may throw NPE if lastUsedIterator is null, since it's never checked 
- (prov) AbstractMapBag.java:97-112 — BagIterator.remove() doesn't decrement itemCount after removing an element, causing the iterato
- (inco) FixedOrderComparator.java:217-229 — FixedOrderComparator.equals() incorrectly includes counter in comparison, causing equals to ret
- (prov) SingletonMap.java:116-122 — SingletonMapIterator.previous() doesn't set canGetSet=true, making getKey()/getValue()/setValue
- (prov) SortedProperties.java:88-89 — SortedProperties.keySet() will throw ClassCastException if the Properties object contains keys 
- (prov) CollectionUtils.java:486 — CollectionUtils.collate() with includeDuplicates=false uses equals() for dedup instead of the c
- (prov) AbstractMapBag.java:206 — AbstractMapBag.add(Object, int) increments modCount even when nCopies is <= 0, causing spurious
- (refu) SingletonListIterator.java:151 — SingletonListIterator.remove() and set() only check nextCalled but previous() doesn't set it, s
- (refu) LinkedMap.java:116 — LinkedMap.LinkedMapList.lastIndexOf() delegates to parent.indexOf(obj) instead of parent.lastIn
- (prov) SwitchTransformer.java:67 — SwitchTransformer.switchTransformer(Map) mutates the input map by calling map.remove(null), cau
- (refu) DualTreeBidiMap.java:131-133 — DualTreeBidiMap.BidiOrderedMapIterator.setValue() modifies the backing map via parent.put() and
- (refu) AbstractMultiValuedMap.java:84-88 — AbstractMultiValuedMap.AsMapEntrySet.remove() throws ClassCastException for non-Map.Entry argum

## apache__dubbo  (Qwen 35 susp | Claude 4 | overlap 3 | Claude-only 1 | Qwen-only 32)

**Overlap (both suspected):**
- `StringUtils#toBoolean` — C: "off" case returns Boolean.TRUE instead of Boolean.FALSE (copy-paste inversion) / Q: "off" should map to Boolean.FALSE, not Boolean.TRUE
- `BitList#randomSelectOne` — C: randomSelectOne divides originSize by cardinality()==0 -> ArithmeticException / Q: randomSelectOne throws ArithmeticException (div by zero) when rootSet cardinality 0 but size>0
- `FastJson2ObjectInput#readObject/readBytes/readLength` — C: single InputStream.read assumed to fill buffer; short read spuriously rejected / Q: readBytes/readObject/readLength use single read() -> spurious IllegalArgumentException on short

**Claude-only:**
- [hig/hig] `StringUtils#getServiceKey` — version segment appended under isNotEmpty(group) guard instead of isNotEmpty(version)

**Qwen-only:**
- (refu) LRUCache.java:128 — The computeIfAbsent method does a lock-free get(key) check, then locks and calls super.computeI
- (prov) NetUtils.java:259 — The condition `address.endsWith(":")` should likely be `address.contains(":")`. With the curren
- (refu) RandomLoadBalance.java:96 — When all weights are equal or when offset matches the last cumulative weight, Arrays.binarySear
- (refu) AsyncRpcResult.java:220 — The waitAndDrain method is called with an absolute nano deadline instead of a relative timeout 
- (prov) ExchangeCodec.java:305 — The error message displays the threshold value twice instead of showing the actual data length 
- (inco) FailbackRegistry.java:399 — The hashCode uses simple addition which can cause collisions for pairs whose hashCodes sum to t
- (prov) LFUCache.java:83 — Updating an existing key resets its frequency to 0, causing frequently used items to become eli
- (refu) LRUCache.java:162-170 — trimToSize() removes the wrong entries - it removes the most recently used entries instead of t
- (prov) LRU2Cache.java:101-108 — TOCTOU race condition: fn.apply() is called outside the lock, and the put() overwrites values i
- (prov) MemoryLimiter.java:211-231 — releaseInterruptibly() can block forever when memory.sum() is 0, causing potential deadlock in 
- (refu) TokenFilter.java:47 — Consumers that don't send a token will be rejected even though the provider token is configured
- (prov) RpcStatus.java:140-142 — Concurrent max tracking uses non-atomic compare-then-set, causing lost updates where a higher e
- (prov) ExecuteLimitFilter.java:50 — Active count leak: generic invocations ($invoke) increment the wrong RpcStatus bucket, causing 
- (prov) CompositeConfiguration.java:73-75 — addConfiguration(int, Configuration) allows duplicate configurations in the list while addConfi
- (prov) SlidingWindow.java:127-129 — Data loss: values added to a pane created when clock goes backward will be lost because the pan
- (prov) AccessLogFilter.java:86 — SimpleDateFormat is not thread-safe; if accessed from multiple threads concurrently, it can pro
- (inco) CIDRUtils.java:83 — CIDRUtils computes wrong network mask due to inverted bit logic - it extracts host bits instead
- (prov) MemoryLimitedLinkedBlockingQueue.java:71 — Memory leak: offer() acquires memory from MemoryLimiter before adding to the underlying queue, 
- (prov) FailoverClusterInvoker.java:134 — Integer overflow when retries is set to Integer.MAX_VALUE causes only 1 invocation instead of t
- (refu) HeaderExchangeHandler.java:88-134 — HeaderExchangeHandler can double-send or corrupt Response state when handler.reply() throws syn
- (prov) WrapperComparator.java:59 — Violates Java Comparator contract (antisymmetry) which can cause undefined behavior in sorted c
- (prov) AbstractDynamicConfiguration.java:216 — Exceptions thrown by config operations are silently swallowed and only logged, returning null i
- (prov) ForkingClusterInvoker.java:97-105 — When a forking invocation gets a result quickly, subsequent async tasks that detect the queue i
- (prov) ConcurrentHashMapUtils.java:42 — When multiple threads concurrently call computeIfAbsent for the same absent key, func.apply(key
- (prov) MockClusterInvoker.java:180-183 — When mock invocation returns a non-AsyncRpcResult but setFutureWhenSync is true, a ClassCastExc
- (refu) MergeableClusterInvoker.java:82 — When all invokers throw non-NoInvokerAvailableAfterFilter exceptions, MergeableClusterInvoker s
- (prov) NetUtils.java:141-149 — getAvailablePort permanently marks ports as used in USED_PORT BitSet but immediately releases t
- (inco) IOUtils.java:166-172 — In read(InputStream is, String encoding) at line 192-202, the InputStreamReader is only closed 
- (prov) AbstractClusterInvoker.java:165 — AbstractClusterInvoker.select() reads sticky parameter from invokers.get(0) which is a provider
- (prov) ConsistentHashLoadBalance.java:109-117 — ConsistentHashLoadBalance.toKey() lacks separators between arguments, causing hash collisions w
- (prov) TimeWindowCounter.java:48-50 — TimeWindowCounter.bucketLivedMillSeconds() can return a value larger than the interval when the
- (prov) DefaultFuture.java:204-207 — DefaultFuture.received() calls t.cancel() on a potentially null timeoutCheckTask, causing NullP

## apache__flink  (Qwen 9 susp | Claude 2 | overlap 1 | Claude-only 1 | Qwen-only 8)

**Overlap (both suspected):**
- `MemorySize#divide` — C: divide(0) guard uses by<0 not by<=0, so zero divisor throws ArithmeticException / Q: divide(long by) guard `by < 0` instead of `by <= 0`, allows division by zero

**Claude-only:**
- [med/hig] `IOUtils#skipFully` — skipFully spins forever at EOF: skip() returns 0 not -1, so ret<0 break is dead

**Qwen-only:**
- (prov) MathUtils.java:100 — isPowerOf2(0) incorrectly returns true instead of false, since (0 & -1) == 0
- (prov) IOUtils.java:304 — deleteFilesRecursively only deletes children but not the directory itself, leaving an empty dir
- (prov) ParameterTool.java:325 — After deserialization, unrequestedParameters is empty instead of containing all keys, so getUnr
- (prov) DirectExecutorService.java:162 — The fake Future for skipped tasks has isDone()=false but get() throws CancellationException imm
- (refu) FileUtils.java:339 — stripFileExtension incorrectly strips filenames when the extension text appears earlier in the 
- (prov) CollectionUtil.java:90-103 — partition() throws ArithmeticException (division by zero) when called with numBuckets=0, instea
- (prov) CollectionUtil.java:65-72 — isEmptyOrAllElementsNull throws NPE when passed a null collection instead of returning true
- (prov) Hardware.java:237-279 — Process resource leak: the Process created by exec() is never destroyed on error paths or in th

## apache__incubator-seata  (Qwen 57 susp | Claude 4 | overlap 4 | Claude-only 0 | Qwen-only 53)

**Overlap (both suspected):**
- `StateMachineRepositoryImpl#getStateMachineById` — C: getStateMachineById caches into stateMachineMapById with name_tenant key instead of id / Q: getStateMachineById() puts items into stateMachineMapById with wrong composite key (name+tenant
- `BranchSession#decode` — C: decode() never reads the lockStatus byte that encode() writes, losing lockStatus on reload / Q: BranchSession.decode() never reads back lockStatus field that encode() writes, data loss on des
- `ParameterParser#getParameters` — C: error branch dereferences ret[i].getClass() while ret[i] is still null, causing NPE / Q: logs ret[i].getClass() but ret[i] is null at that point, causing NPE in the error message
- `ConsistentHashLoadBalance.SHA256Hash#hash` — C: update(key)+digest(key) hashes key||key rather than key, wrong SHA-256 / Q: SHA256Hash.hash() adds key bytes twice (via update and digest), producing incorrect hash values

**Qwen-only:**
- (prov) CollectionUtils.java:251 — Values containing the "=" character are silently dropped during map decoding, causing data loss
- (prov) NetUtil.java:176 — NullPointerException when the InetAddress in the InetSocketAddress is null (unresolved address)
- (prov) GlobalSession.java:211 — GlobalSession.isTimeout() returns true immediately when timeout is not set (defaults to 0), cau
- (prov) SizeUtil.java:46 — SizeUtil.size2Long doesn't validate that the extracted number is positive, so inputs like '-1k'
- (prov) Lz4Util.java:43 — Lz4Util compress and decompress silently swallow IOExceptions, returning incomplete or empty da
- (prov) RejectedPolicies.java:45 — RejectedPolicies.runsOldestTaskPolicy causes infinite recursion (StackOverflowError) when the q
- (prov) ConsistentHashLoadBalance.java:139 — MessageDigest instance is shared across threads without synchronization, causing race condition
- (prov) ConsistentHashLoadBalance.java:140 — SHA256Hash.hash uses different charsets for update() and digest(), causing incorrect hash value
- (prov) GlobalSession.java:146 — GlobalSession.remove(BranchSession) throws NPE when branchSessions is null (lazy loading), beca
- (refu) KryoSerializer.java:50 — KryoSerializer.deserialize() closes the Input stream before reading from it, causing all deseri
- (prov) FileLocker.java:89 — Negative hashCode values produce negative bucket IDs, causing incorrect bucket placement in the
- (prov) AsyncEventBus.java:50 — AsyncEventBus.offer() throws NPE when threadPoolExecutor is null (never set via setThreadPoolEx
- (inco) DeflaterUtil.java:38 — DeflaterUtil.decompress() may silently truncate output larger than BUFFER_SIZE since the Inflat
- (prov) DurationUtil.java:79 — DurationUtil.doParse uses replace(unit, "") which replaces all occurrences of the unit in the s
- (prov) DefaultGlobalTransaction.java:276 — ProcessContextImpl.setVariable() delegates to parent when the child doesn't have the variable l
- (prov) ResourceLock.java:43-46 — ResourceLock.obtain() returns 'this' instead of a new guard object, meaning multiple threads ca
- (prov) StateMachineParserImpl.java:99 — StateMachineParserImpl.parse() throws NPE when the JSON doesn't contain a "States" key.
- (prov) FileConfiguration.java:341 — FileListener uses non-thread-safe HashMap for dataIdMap that is accessed concurrently by multip
- (prov) Id.java:78 — Id.getMeterKey() only outputs tag values without keys, causing meter key collisions when differ
- (refu) TransactionWriteStore.java:88 — No bug found in TransactionWriteStore, the encode/decode logic is correct.
- (prov) RoundRobinLoadBalance.java:36 — RoundRobinLoadBalance.select() throws ArithmeticException when invokers list is empty due to di
- (prov) RandomLoadBalance.java:33 — RandomLoadBalance.select() throws IllegalArgumentException when invokers list is empty.
- (prov) XIDLoadBalance.java:50 — XIDLoadBalance.select() throws unhandled NumberFormatException if port in xid is not a valid in
- (prov) LeastActiveLoadBalance.java:36 — LeastActiveLoadBalance.select() throws IllegalArgumentException when invokers list is empty.
- (refu) GzipUtil.java:55 — This is actually correct, not a bug. Read returns -1 on EOF and >= 0 for bytes read.
- (prov) CollectionUtils.java:347 — mapToJsonString only recursively handles HashMap values, not other Map implementations, produci
- (inco) AsyncEventBus.java:50 — AsyncEventBus.offer() silently swallows exceptions thrown by eventConsumer.process() in async e
- (prov) KryoSerializerFactory.java:102-110 — KryoSerializerFactory BlobSerializer and ClobSerializer silently swallow SQLException during wr
- (prov) SessionHolder.java:140-147 — SessionHolder.init() calls EnhancedServiceLoader.load() twice for ROOT_SESSION_MANAGER in FILE 
- (prov) NettyPoolKey.java:124-125 — NettyPoolKey.toString() throws NPE when message field is null.
- (prov) LowerCaseLinkHashMap.java:123-124 — LowerCaseLinkHashMap entrySet() returns lowercase keys while keySet() returns original keys, vi
- (prov) NettyPoolableFactory.java:53-88 — NettyPoolableFactory.makeObject() leaks tmpChannel when key.getMessage() is null (throws before
- (prov) GlobalTransactionalInterceptorParser.java:37 — GlobalTransactionalInterceptorParser methodsToProxy is shared instance field that accumulates a
- (prov) ConfigurationFactory.java:268-272 — OldConfigurationInvocationHandler.invoke() throws NPE when method argument is null (args[i].get
- (prov) TokenBucketLimiter.java:104-107 — TokenBucketLimiter.canPass() throws NPE when enable is false because bucket is never initialize
- (prov) AbstractNettyRemoting.java:109 — AbstractNettyRemoting.processorTable uses non-thread-safe HashMap, causing potential Concurrent
- (prov) ProcessContextImpl.java:39-62 — ProcessContextImpl.getVariable/setVariable have TOCTOU race condition with containsKey() follow
- (prov) StringUtils.java:249-254 — StringUtils.toString() throws ArrayIndexOutOfBoundsException when handling anonymous class that
- (prov) CycleDependencyHandler.java:144-147 — CycleDependencyHandler uses identityHashCode for cycle detection which can produce false positi
- (refu) BaseHttpChannelHandler.java:44-46 — BaseHttpChannelHandler registers multiple shutdown hooks when subclassed, creating unnecessary 
- (prov) XID.java:55-63 — XID.generateXID() produces malformed XID containing literal 'null' if ipAddress is not initiali
- (prov) AbstractNettyRemotingClient.java:331-334 — AbstractNettyRemotingClient.getXid() fails to read private 'xid' fields because setAccessible(t
- (prov) HttpRequestFilterChain.java:27 — HttpRequestFilterChain.currentIndex is mutable instance state that can be corrupted by concurre
- (prov) EnhancedServiceLoader.java:363-372 — EnhancedServiceLoader.load(activateName, Object[] args, ...) throws NPE when args array contain
- (prov) CollectionUtils.java:272-278 — CollectionUtils.computeIfAbsent incorrectly treats null map values as absent, causing repeated 
- (prov) GlobalTransactionScanner.java:103-106,223 — GlobalTransactionScanner static fields (PROXYED_SET, NEED_ENHANCE_BEAN_NAME_SET) cause state le
- (prov) BranchSession.java:86-89 — BranchSession constructor with non-AT branchType creates immutable lockHolder (Collections.empt
- (refu) FiniteTerminationRule.java:68 — FiniteTerminationRule.validate() throws NPE when a cycle state is not in nextStateNameMap (e.g.
- (prov) CollectionUtils.java:272-278 — CollectionUtils.computeIfAbsent() throws NPE when called with null map, since it doesn't check 
- (prov) ProcessControllerImpl.java:42 — ProcessControllerImpl.process() throws NPE when businessProcessor is null because setBusinessPr
- (refu) CollectionUtils.java:272-278 — CollectionUtils.computeIfAbsent() throws IllegalArgumentException when the mappingFunction retu
- (refu) FiniteTerminationRule.java:98-100 — FiniteTerminationRule.validate() throws IndexOutOfBoundsException or produces incorrect cycle d
- (prov) StoreConfig.java:static — StoreConfig static initializer requires Spring environment, making it impossible to create Bran

## apache__rocketmq  (Qwen 31 susp | Claude 1 | overlap 1 | Claude-only 0 | Qwen-only 30)

**Overlap (both suspected):**
- `PopCheckPoint#compareTo` — C: compareTo casts (long startOffset diff) to int, overflow flips ordering; use Long.compare / Q: PopCheckPoint.compareTo() casts long subtraction to int, overflow → wrong ordering when diff > 

**Qwen-only:**
- (prov) MessageDecoder.java:156-168 — When CRC32 is negative, the encoded string will be all zeros, making CRC32 verification useless
- (prov) AttributeParser.java:47-49 — Attribute values containing '=' character will be truncated, losing part of the value.
- (prov) RecallMessageHandle.java:90-91 — Accessing items[0] before validating items.length < 5 in the combined condition causes ArrayInd
- (prov) MessageClientIDSetter.java:123 — For days beyond ~24 of the month, the time diff overflows int, causing negative values in the u
- (prov) TimerWheel.java:87-88 — TimerWheel.shutdown() throws NullPointerException when snapOffset >= 0 because fileChannel is n
- (prov) ConsumerOffsetManager.java:94 — Topics containing '@' character will not be properly cleaned because split('@') produces more t
- (prov) SubscriptionData.java:117-150 — SubscriptionData objects with same topic, subString, tagsSet, codeSet, classFilterMode, express
- (prov) ProcessQueue.java:320-331 — ProcessQueue.hasTempMessage() returns true on InterruptedException, incorrectly reporting that 
- (prov) TopicMessageType.java:50-52 — TopicMessageType.parseFromMessageProperty throws NullPointerException when messageProperty is n
- (prov) KeyBuilder.java:65-72 — KeyBuilder.parseGroup returns incorrect group name when the input is not a retry topic because 
- (prov) KeyBuilder.java:55-62 — KeyBuilder.parseNormalTopic fails to extract normal topic when the topic name contains '+' char
- (refu) FileWatchService.java:109-110 — FileWatchService.md5Digest uses a shared MessageDigest without reset(), causing cumulative hash
- (refu) TransactionalMessageServiceImpl.java:307-308 — In TransactionalMessageServiceImpl.getOpMessage, when moreData is null, the totalSize is decrem
- (prov) PopProcessQueue.java:52-54 — PopProcessQueue.decFoundMsg() increments the counter instead of decrementing it, causing waitAc
- (prov) ConsumerOffsetManager.java:330-341 — ConsumerOffsetManager.queryMinOffsetInAllGroup() unexpectedly removes entries from offsetTable 
- (prov) AckMessageProcessor.java:411 — Tight spin loops without sleep/yield in while(!tryLock()) cause unnecessary CPU consumption und
- (prov) KeyBuilder.java:65-73 — KeyBuilder.parseGroup(String) incorrectly parses group name when topic contains "+" character i
- (refu) LatencyFaultToleranceImpl.java:62 — LatencyFaultToleranceImpl.detectByOneRound() modifies faultItemTable (remove) while iterating o
- (prov) PopAckConstants.java:22-25 — PopAckConstants.ackTimeInterval and lockTime are mutable static fields without synchronization,
- (prov) DefaultBrokerHeartbeatManager.java:59 — DefaultBrokerHeartbeatManager.start() will NPE if called before initialize() as scheduledServic
- (refu) IndexFile.java:176-183 — The indexKeyHashMethod handles Integer.MIN_VALUE edge case by checking for negative result. Thi
- (refu) TimerWheel.java:306-323 — TimerWheel.reviseSlot() ByteBuffer position tracking error when lastPos == IGNORE causes data c
- (prov) DefaultPromise.java:175-182 — DefaultPromise.getValueOrThrowable() calls notifyListeners() on every get() call, causing regis
- (refu) AutoSwitchHAService.java:101-119 — AutoSwitchHAService.removeConnection() clear-then-add pattern on syncStateSet is fragile and co
- (prov) QueueOffsetOperator.java:54-57 — QueueOffsetOperator.increaseQueueOffset() and increaseBatchQueueOffset() have a race condition 
- (prov) PopCheckPoint.java:196-205 — PopCheckPoint.parseRePutTimes() returns Byte.MAX_VALUE (127) as error sentinel, which is ambigu
- (prov) LatencyFaultToleranceImpl.java:62 — LatencyFaultToleranceImpl.detectByOneRound() always evaluates the time condition as true becaus
- (prov) IndexService.java:122-123 — IndexService.deleteExpiredFile() skips the last index file when checking for deletion, potentia
- (refu) SyncStateInfo.java:88-90 — SyncStateInfo.removeFromSyncState() throws UnsupportedOperationException because syncStateSet i
- (refu) StatefulAuthorizationStrategy.java:71 — StatefulAuthorizationStrategy.buildKey() has unresolvable {} placeholder in exception message, 

## apache__shardingsphere  (Qwen 9 susp | Claude 1 | overlap 1 | Claude-only 0 | Qwen-only 8)

**Overlap (both suspected):**
- `RetryExecutor#isTimeout` — C: isTimeout lacks early-return guard, does a spurious Thread.sleep before returning when timeout  / Q: RetryExecutor always sleeps at least once even when timeout already exceeded

**Qwen-only:**
- (refu) TypedProperties.java:60 — NullPointerException when getting a property value that threw TypedPropertyValueException durin
- (inco) MemoryMergedResult.java:59 — NullPointerException when calling getValue() on an empty MemoryMergedResult because currentResu
- (prov) ConnectionTransaction.java:107 — NullPointerException when calling begin(), commit(), or rollback() on a ConnectionTransaction w
- (prov) SnowflakeKeyGenerateAlgorithm.java:94 — Snowflake keys may be duplicated or incorrectly ordered if system timezone offset changes betwe
- (prov) DatabaseMetaDataManager.java:103 — NullPointerException or incorrect behavior in dropSchema because getSchema is called on a schem
- (inco) AbstractSQLBuilder.java:45 — Unintended mutation of the sqlTokens list passed to constructor, potentially causing issues if 
- (inco) WeightLoadBalanceAlgorithm.java:126 — NullPointerException in getWeightValue when an available target name is not present in the weig
- (inco) ShardingSphereTransactionManagerEngine.java:64 — Method parameter shadows instance field, causing the null check to be skipped when LOCAL type i

## apache__skywalking  (Qwen 23 susp | Claude 3 | overlap 2 | Claude-only 1 | Qwen-only 21)

**Overlap (both suspected):**
- `State.LABEL_VALUE_SLASH#nextState` — C: Escape branch decodes char then line 119 re-appends raw backslash+char, corrupting value / Q: LABEL_VALUE_SLASH appends both escaped char AND raw backslash+char, doubled output
- `ConnectUtils#parse` — C: replace(",","") strips ALL commas not just leading one, breaking multi-host strings / Q: replace(",","") removes ALL commas instead of just leading one, destroying connect strings

**Claude-only:**
- [med/hig] `StringUtil#trim` — trim(str,ch) throws SIOOBE (negative length) when str is entirely ch, len>=2

**Qwen-only:**
- (prov) BooleanUtils.java:37 — NullPointerException when booleanToValue is called with null Boolean argument due to auto-unbox
- (prov) StringUtil.java:86 — trim("", ch) returns null instead of "", which could cause NPE downstream
- (prov) TextParser.java:111 — ArrayIndexOutOfBoundsException when parsing Prometheus TYPE line missing the type value
- (prov) VirtualThreadScheduledExecutor.java:237 — NPE when cancel/get/isDone/isCancelled called on VirtualScheduledFuture before delegate is set
- (prov) GRPCClient.java:112 — NullPointerException in GRPCClient.shutdown() when connect() was never called and channel is nu
- (prov) StringUtil.java:38 — StringUtil.join produces unexpected delimiters for null array elements - nulls still produce de
- (prov) State.java:63 — Label with no value (e.g., metric{label_name}) in LABEL_NAME state hits '}' and transitions to 
- (prov) FieldsHelper.java:105 — ArrayList initialized with m.groupCount() (number of regex groups) instead of the actual number
- (inco) RunningRule.java:324 — transformValues() adds a new map entry to result for each metric in the value map, instead of g
- (refu) PartitionSelector.java:55 — typeHash() partition selector routes all instances of the same class to the same partition, ign
- (inco) MultipleFilesChangeMonitor.java:246 — When file read fails with IOException, lastModifiedTimestamp is still updated in finally block,
- (prov) BulkProcessor.java:149 — flush() blocks on future.join() in the scheduler thread, preventing periodical flush from runni
- (prov) GRPCClient.java:98 — Multiple calls to connect() leak previous ManagedChannel resources since old channel is never s
- (prov) TypeCastUtil.java:40 — Error message incorrectly says the cast type 'is legal' when it is actually illegal, confusing 
- (prov) KafkaExportProducer.java:41-52 — Race condition in getProducer() allows multiple threads to create duplicate KafkaProducer insta
- (inco) LimitedSizeBufferedData.java:55-65 — Top-N buffer algorithm assumes sorted list but elements are appended unsorted, causing valid va
- (prov) ThroughputWeightedBalancer.java:69-71 — LPT balancer sorts partitions by truncated int throughput but assigns using long throughput, ca
- (refu) AlarmMQEVisitor.java:203 — AlarmMQEVisitor.initMetricsValues() uses 'return' instead of 'continue' when encountering unsup
- (prov) VirtualThreadScheduledExecutor.java:137-143 — scheduleAtFixedRate does not handle InterruptedException from sleepUntil, causing unhandled exc
- (refu) TraceAnalyzer.java:43,50 — TraceAnalyzer analysisListeners list grows without bound because createSpanListeners appends ne
- (prov) MQEVisitorBase.java:235 — parseLabelValue skips splitting when separator is at position 0, treating the entire string as 

## apolloconfig__apollo  (Qwen 42 susp | Claude 1 | overlap 1 | Claude-only 0 | Qwen-only 41)

**Overlap (both suspected):**
- `ItemService#getGrayNamespaceItemValueLengthLimit` — C: Gray namespace limit computed against itself, not parent; parent's larger limit never inherited / Q: Gray namespace limit compared against itself; parent's larger limit never applied

**Qwen-only:**
- (prov) BeanUtils.java:111 — If the list contains mixed types where the field from the first element's class doesn't exist o
- (prov) CaseInsensitiveMapWrapper.java:32 — In Turkish locale, 'I'.toLowerCase() returns 'ı' (dotless i) instead of 'i', causing case-insen
- (prov) GrayReleaseRulesHolder.java:227 — Race condition where both old and new reversed cache entries exist simultaneously during rule r
- (prov) ConfigServiceWithCache.java:218 — When configServiceCacheKeyIgnoreCase is enabled, the cache loader queries the DB with a lowerca
- (prov) ItemService.java:213 — ItemService.update will throw NullPointerException when trying to update an item that doesn't e
- (prov) ClusterService.java:125 — ClusterService.update will throw NullPointerException when trying to update a cluster that does
- (prov) DefaultIncrementalSyncService.java:49 — Returning mutable cached list allows caller to corrupt the cache, causing incorrect change dete
- (prov) AppNamespaceService.java:146 — AppNamespaceService.update throws IllegalArgumentException when updating a non-existent namespa
- (prov) BeanUtils.java:65 — BeanUtils.transform uses the deprecated Class.newInstance() instead of clazz.getDeclaredConstru
- (prov) NamespaceService.java:334 — NamespaceService.update throws IllegalArgumentException when updating a non-existent namespace,
- (prov) NotificationController.java:106 — When a release message triggers notification, all watching clients receive the same namespace n
- (prov) ItemController.java:180 — ItemController.delete throws NullPointerException when the item's namespace has been soft-delet
- (prov) CommitService.java:65 — CommitService.findByKey SQL LIKE pattern is not properly escaped for special characters in the 
- (prov) NamespaceUtil.java:36 — Namespace suffix filter fails in Turkish locale due to toLowerCase() without Locale.ROOT, preve
- (prov) ConfigServiceWithCache.java:116-117 — Turkish locale bug in ConfigServiceWithCache: toLowerCase() without Locale.ROOT causes cache ke
- (inco) ConfigChangeContentBuilder.java:44 — ConfigChangeContentBuilder.updateItem throws NPE when oldItem.getValue() is null, because it ca
- (refu) ConfigFileController.java:307 — Turkish locale bug in ConfigFileController.determineNamespaceFormat causes incorrect format det
- (prov) NamespaceService.java:360 — NamespaceService.transformItem2BO throws NPE when item value is null, because newValue.equals(o
- (prov) ClientAuthenticationFilter.java:80-83 — Observable secrets preCheck in ClientAuthenticationFilter doesn't block unauthorized requests. 
- (inco) ConfigsExportService.java:337 — ConfigsExportService.writeToZip uses platform default charset instead of UTF-8, causing encodin
- (prov) NotificationController.java:144-170 — NotificationController.handleMessage may not properly trigger all watching clients when a relea
- (prov) NamespaceController.java:88 — NamespaceController.get throws NotFoundException.itemNotFound instead of NotFoundException.name
- (prov) ItemService.java:362 — ItemService.isModified throws NPE when sourceValue is null, because sourceValue.equals(targetVa
- (refu) ReleaseController.java:107-113 — ReleaseController.getLatest may throw NPE or return unexpected result when there is no active r
- (prov) ItemService.java:157-163 — ItemService.getItemInfoBySearch throws NPE when key or value is null, because key.isEmpty() is 
- (prov) ItemService.java:223-232 — ItemService.checkItemValueLength throws NPE when namespaceService.findOne returns null, because
- (prov) FileTextResolver.java:43 — FileTextResolver.resolve throws NPE when configText is null because configText.equals() is call
- (prov) ItemController.java:159-165 — ItemController.findItems throws NPE in the lastModifiedTime comparator when o1.getDataChangeLas
- (prov) ConfigToFileUtils.java:43 — ConfigToFileUtils.fileToString leaks resources because the BufferedReader (and underlying Input
- (prov) ConfigServiceWithCache.java:195 — ConfigServiceWithCache.findReleasesByReleaseKeys returns null on exception instead of an empty 
- (refu) GlobalDefaultExceptionHandler.java:69-73 — GlobalDefaultExceptionHandler badRequest handler accepts ServletException but handles HttpReque
- (prov) ClusterService.java:108 — ClusterService.delete passes empty string to clusterNotExists error message instead of the clus
- (refu) NotificationControllerV2.java:329 — NotificationControllerV2.retrieveNamespaceFromReleaseMessage throws IndexOutOfBoundsException w
- (prov) NamespaceBranchService.java:65 — When branch already exists, NamespaceBranchService.createBranch throws a misleading 'namespace 
- (prov) Env.java:212 — Env.equals() throws RuntimeException when comparing two Env objects with the same name, instead
- (prov) ReleaseMessageServiceWithCache.java:127-133 — In ReleaseMessageServiceWithCache.handleMessage, when gap > 1, loadReleaseMessages is called to
- (prov) ConfigsImportService.java:136 — ArrayIndexOutOfBoundsException when processing ZIP entries with path depth of 2 (info.length ==
- (prov) BeanUtils.java:254 — copyEntityProperties misses dataChangeLastModifiedBy in ignored properties, causing the wrong o
- (prov) ReleaseOperation.java:29 — Typo in constant name MATER_ROLLBACK_MERGE_TO_GRAY should be MASTER_ROLLBACK_MERGE_TO_GRAY, cau
- (prov) ClientAuthenticationFilter.java:146 — When timestamp header is missing/invalid, requestTimeMillis remains 0 causing Math.abs(System.c
- (prov) AdminService.java:70 — Child/branch clusters are not deleted when an app is deleted, because findParentClusters only r

## binarywang__WxJava  (Qwen 16 susp | Claude 2 | overlap 1 | Claude-only 1 | Qwen-only 15)

**Overlap (both suspected):**
- `FileUtils#imageToBase64ByStream` — C: in.available() + single unchecked in.read() truncates stream -> corrupted Base64 / Q: Incomplete read from InputStream -> corrupted/truncated base64 encoding

**Claude-only:**
- [med/hig] `RedisTemplateSimpleDistributedLock#unlock` — reentrancy advertised but no hold count -> single unlock DELs multiply-acquired lock

**Qwen-only:**
- (refu) WxMessageInMemoryDuplicateChecker.java:74 — ConcurrentModificationException or entries not being removed during the cleanup loop, causing m
- (prov) RedisTemplateSimpleDistributedLock.java:80 — Thread incorrectly believes it holds the lock when another thread acquired it after expiration,
- (prov) FileUtils.java:37 — Caller's InputStream is unexpectedly closed after createTmpFile returns, causing IOExceptions o
- (prov) PKCS7Encoder.java:47 — ArrayIndexOutOfBoundsException when PKCS7Encoder.decode is called with an empty byte array.
- (prov) AesUtils.java:126 — Cryptographic operation silently fails, returning null which may bypass signature validation or
- (prov) SignUtils.java:230 — NullPointerException when xmlBean2Map is called on a bean whose class hierarchy doesn't match t
- (prov) SignUtils.java:218 — NullPointerException in checkSign when HMAC-SHA256 signing fails internally and returns null.
- (inco) BeanUtils.java:35 — NullPointerException when checkRequiredFields is called on a bean whose class has no superclass
- (refu) WxMaCryptUtils.java:65 — Security.addProvider(new BouncyCastleProvider()) is called on every invocation of decryptAnothe
- (refu) DefaultOkHttpClientBuilder.java:122 — Two threads can both enter prepare() simultaneously if they both see prepared=false, leading to
- (prov) DataUtils.java:21 — Secrets at the end of URLs (without trailing &) are not masked by the regex, potentially leakin
- (refu) WxMaCryptUtils.java:65 — Base64.decodeBase64(sessionKey.getBytes(UTF_8)) corrupts the key by applying UTF-8 encoding bef
- (inco) EntPayServiceImpl.java:193 — Temporary PEM files created by buildPublicKeyFile accumulate on disk and are never deleted, cau
- (prov) GsonHelper.java:111 — If the JSON property exists but is not an array, ClassCastException is thrown instead of gracef
- (refu) HttpResponseProxy.java:56 — Unreachable code path - UnsupportedEncodingException can never be thrown for StandardCharsets.U

## brettwooldridge__HikariCP  (Qwen 22 susp | Claude 2 | overlap 2 | Claude-only 0 | Qwen-only 20)

**Overlap (both suspected):**
- `HikariConfig#setCredentialsProviderClassName` — C: setCredentialsProviderClassName writes exceptionOverrideClassName field (copy-paste bug) / Q: setCredentialsProviderClassName() sets wrong field (exceptionOverrideClassName)
- `HikariConnectionProvider#HikariConnectionProvider` — C: Deprecation warning guard uses '>= 1' on compareTo so 4.3.6 exact version skipped / Q: Deprecation warning not shown for 4.3.6 because compareTo uses >= 1 instead of >= 0

**Qwen-only:**
- (prov) ConcurrentBag.java:398-408 — ArrayIndexOutOfBoundsException when any PoolEntry is in STATE_RESERVED (-2) or STATE_REMOVED (-
- (prov) ProxyLeakTask.java:79-82 — NegativeArraySizeException in ProxyLeakTask.run() when exception.getStackTrace() returns fewer 
- (refu) HikariConfig.java:431 — Not a bug - false positive. Moving on.
- (refu) ProxyDatabaseMetaData.java:74 — ProxyResultSet.getStatement() returns null when the underlying ResultSet's getStatement() retur
- (prov) HikariJNDIFactory.java:48 — NullPointerException when JNDI Reference's getContent() returns null, causing HikariJNDIFactory
- (prov) HikariConfig.java:441 — Resource leak: InitialContext created but never closed in getObjectOrPerformJndiLookup(), leadi
- (prov) HikariConnectionProvider.java:69 — NullPointerException in HikariConnectionProvider constructor if Hibernate's Version.getVersionS
- (prov) ProxyConnection.java:461 — ProxyConnection.setSchema() reads back from delegate.getSchema() instead of storing the paramet
- (prov) HikariPool.java:510 — The exception cause is silently dropped from the debug log message because there's no correspon
- (prov) ProxyStatement.java:228-235 — NPE occurs when Statement.getGeneratedKeys() returns null and the null ResultSet is wrapped in 
- (prov) HikariConfigurationUtil.java:56 — ClassCastException in HikariConfigurationUtil when props.get(key) returns a non-String value, a
- (refu) PrometheusHistogramMetricsTracker.java:84-90 — Three Histogram metrics (connection acquired, usage, creation) are never registered to the Coll
- (prov) HikariConnectionProvider.java:115 — NPE in HikariConnectionProvider.closeConnection() when passed a null connection (e.g., when hds
- (prov) PoolBase.java:340 — InitialContext resource leak in PoolBase.initializeDataSource() - created but never closed when
- (prov) HikariJNDIFactory.java:74-76 — InitialContext resource leak in HikariJNDIFactory.lookupJndiDataSource() - if lookup throws Nam
- (prov) HikariConfig.java:58 — The static `unitTest` field in HikariConfig causes test isolation issues and can mask validatio
- (prov) RequestBoundariesTest.java:16 — RequestBoundariesTest shares a static config across tests and doesn't clean up the system prope
- (inco) ExceptionTest.java:156-159 — ExceptionTest.testLastErrorTimeout() has a copy-paste error where `causeCause = e.getCause()` s
- (refu) MetricsTrackerTest.java:48-52 — Actually, on closer inspection this test is correct - `recordBorrowTimeoutStats` does call `rec
- (prov) HikariConfigTest.java:87 — TestAppender.log field is null-initialized, causing first log message to have "null" prefix due

## bumptech__glide  (Qwen 12 susp | Claude 3 | overlap 1 | Claude-only 2 | Qwen-only 11)

**Overlap (both suspected):**
- `LruCache#put` — C: put uses itemSize>=maxSize, wrongly rejecting an item whose size equals maxSize / Q: size==maxSize items always rejected; check should be itemSize > maxSize

**Claude-only:**
- [hig/hig] `LruCache#trimToSize` — trimToSize NPEs on toRemove.size when evicting a documented null-valued entry
- [low/low] `MultiClassKey#equals` — equals/hashCode deref first/second without null check; no-arg ctor instance NPEs

**Qwen-only:**
- (prov) GroupedLinkedMap.java:32,45 — When a key is reused in put() or get(), the caller's key object is incorrectly recycled into th
- (inco) LazyHeaders.java:57-71 — When a non-empty header is followed by empty headers, a trailing comma is incorrectly appended 
- (prov) GlideUrl.java:141-147 — GlideUrl.hashCode() uses 0 as an uninitialized sentinel, but 0 is a valid hashCode result. This
- (inco) CachedHashCodeArrayMap.java:50-55 — CachedHashCodeArrayMap caches hash as 0 which is indistinguishable from uninitialized, so the c
- (refu) EngineJob.java:457-458 — ResourceCallbacksAndExecutors.contains/remove uses synthetic temporary objects with equals that
- (prov) MultiClassKey.java:37-39 — MultiClassKey.toString() omits the third field, making debugging misleading since two equal obj
- (refu) LruCache.java:144 — LruCache.put() can NPE at old.value.equals(item) when item is null and there's an existing entr
- (inco) ModelCache.java:110-125 — ModelKey.equals() and hashCode() will NPE if model is null, since there's no null guard before 
- (refu) ActiveResources.java:123-124 — ActiveResources.cleanupActiveReference() can NPE on listener field if called before setListener
- (refu) HttpGlideUrlLoader.java:48 — HttpGlideUrlLoader always uses width=0 and height=0 for model cache lookups, making the ModelCa
- (refu) RequestManagerRetriever.java:207 — RequestManagerRetriever.findSupportFragment() will fail to find the correct support fragment if

## chinabugotech__hutool  (Qwen 15 susp | Claude 1 | overlap 1 | Claude-only 0 | Qwen-only 14)

**Overlap (both suspected):**
- `XMLTokener#unescapeEntity` — C: Malformed numeric entity "&#;" makes unescapeEntity throw SIOOBE/NFE instead of JSONException / Q: SIOOBE in XMLTokener.unescapeEntity when entity is just "#" (charAt(1) without length check)

**Qwen-only:**
- (prov) JSONTokener.java:142 — Null characters (\u0000) in JSON input would be incorrectly treated as end-of-stream, causing p
- (prov) NioServer.java:140 — NullPointerException when a client connects and sends data before setChannelHandler is called, 
- (prov) JSONObjectIter.java:30 — ClassCastException when jsonIter() is used on a JSONArray that contains non-JSONObject elements
- (refu) WordTree.java:264 — When a word starts with a stop character, the outer loop skips the next character, potentially 
- (refu) InternalJSONUtil.java:94-97 — The stringToValue function treats empty strings as null, which is likely correct for unquoted v
- (prov) JWT.java:409-413 — Calling JWT.verify() without providing a signer or key will accept any JWT token as valid, allo
- (prov) BitMapBloomFilter.java:48-50 — The BitMapBloomFilter(int m, BloomFilter... filters) constructor calls this(m) which creates an
- (inco) AcceptHandler.java:22-26 — NullPointerException in AioServer when client connects without setIoAction being called, since 
- (prov) DialectFactory.java:207 — NullPointerException thrown when getDialect(null) is called, because synchronized(ds) on a null
- (prov) DesensitizedUtil.java:129 — DesensitizedUtil.desensitized(str, DesensitizedType.USER_ID) always returns "0" regardless of i
- (prov) GlobalThreadPool.java:56-82 — Race condition in GlobalThreadPool where executor reference changes in init()/shutdown() may no
- (refu) IdcardUtil.java:508-510 — NullPointerException in IdcardUtil.getAgeByIdCard when idcard is too short (< 15 chars) because
- (prov) GlobalHeaders.java:26 — Thread-safety bug in GlobalHeaders where concurrent HTTP requests across multiple threads may c
- (prov) TimingWheel.java:39 — TimingWheel tasks may be scheduled to wrong time slots due to visibility issues with non-volati

## dbeaver__dbeaver  (Qwen 15 susp | Claude 3 | overlap 2 | Claude-only 1 | Qwen-only 13)

**Overlap (both suspected):**
- `OffsetKeyedTreeMap#nodesIteratorAt / deleteNode` — C: Iterator dispatches on raw size incl. tombstones; empty map yields a phantom null-content entry / Q: nodesIteratorAt() uses raw size field not size(), wrong branch when tombstones exist
- `DataExporterXML#escapeXmlElementName` — C: escapeXmlElementName("") throws SIOOBE on charAt(0); reachable from empty column/source name / Q: escapeXmlElementName() throws SIOOBE on empty string, charAt(0) with no length check

**Claude-only:**
- [med/hig] `OffsetKeyedTreeMap#deleteNode` — Two-children delete with successor.left never physically removes node; tombstones accumulate

**Qwen-only:**
- (inco) ChatTruncator.java:112-117 — Token budget underestimation: when an extra (non-pinned) message is truncated, the suffix token
- (refu) Diff.java:127-128 — Potential storage collision in Myers diff algorithm when delta=0, but re-examination shows FV a
- (prov) Diff.java:198-203 — When processFragment handles empty arrays directly (aLen=0 or bLen=0), the dmax check is bypass
- (inco) DataExporterCSV.java:268 — Extra trailing delimiter in CSV output when row.length exceeds columns.length, because the deli
- (inco) QueryReconstructor.java:223-226 — ArrayIndexOutOfBoundsException when all comments are positioned before the last token, because 
- (refu) DataExporterCSV.java:131 — Not a real bug - the null check is intentional for append mode support. Retracting.
- (prov) SQLQueryDangerousDetectionTest.java:44 — Malformed SQL in test: DELETE has SET clause (UPDATE syntax), causing parser to fail silently. 
- (refu) SQLQueryCompletionContext.java:1602-1603 — False alarm - the || short-circuit evaluation protects against empty nameNodes. Not a bug.
- (inco) PostgreIntervalValueHandler.java:121-124 — PostgreSQL interval display string has seconds appended twice (once raw, once formatted), produ
- (inco) PostgreIntervalValueHandler.java:170 — Fractional seconds in PostgreSQL interval are truncated to 0 milliseconds due to (long) cast of
- (inco) DBNUtilsTest.java:102-107 — Test method assertCorrectSortingWithCase incorrectly calls assertCorrectSortingIgnoreCase inter
- (prov) ProcedureBodyExtractorTest.java:110 — Invalid escape sequence `\s` in Java text block causes compilation failure, preventing the func
- (inco) DataExporterCSV.java:337-339 — Standalone carriage return characters (\\r without \\n) are not escaped even when lineFeedEscap

## google__gson  (Qwen 10 susp | Claude 1 | overlap 1 | Claude-only 0 | Qwen-only 9)

**Overlap (both suspected):**
- `UtcDateTypeAdapter#parse` — C: Fractional-seconds branch reads exactly 3 digits, rejecting other-length ISO-8601 fractions / Q: UtcDateTypeAdapter fails to parse ISO 8601 dates with sub-3-digit milliseconds; parser expects 

**Qwen-only:**
- (prov) PostConstructAdapterFactory.java:34-45 — PostConstructAdapterFactory only invokes one @PostConstruct method even when multiple exist acr
- (prov) InterceptorFactory.java:59-63 — InterceptorFactory.InterceptorAdapter.read() calls postDeserialize on null result, which can ca
- (prov) JsonWriter.java:719-727 — JsonWriter.close() closes the underlying writer even when the document is incomplete and an IOE
- (prov) RuntimeTypeAdapterFactory.java:308-311 — RuntimeTypeAdapterFactory with maintainType=true fails to include the type field when serializi
- (refu) ProtoTypeAdapter.java:273 — ProtoTypeAdapter.serialize() has ret.add(name, array) inside the loop instead of after it, caus
- (prov) EnumTypeAdapter.java:120-122 — EnumTypeAdapter.read() silently returns null for unknown enum values instead of throwing an exc
- (prov) UtcDateTypeAdapter.java:208 — UtcDateTypeAdapter will reject valid timezone offsets like "+00:00" because TimeZone.getTimeZon
- (pend) DefaultDateTypeAdapter.java — Nothing confirmed yet
- (refu) RuntimeTypeAdapterFactory.java:269 — When `maintainType=true` and the target subtype class has a field with the same name as `typeFi

## google__guava  (Qwen 4 susp | Claude 0 | overlap 0 | Claude-only 0 | Qwen-only 4)


**Qwen-only:**
- (prov) Streams.java:396-409 — Resource leak: forEachPair fails to close input streams in the non-parallel path, causing resou
- (prov) ByteStreams.java:778-784 — LimitedInputStream.skip can skip past the limit when wrapping a FileInputStream, allowing reads
- (refu) LocalCache.java:2581-2592 — LocalCache.Segment.drainRecencyQueue() uses O(n) accessQueue.contains() inside a loop, causing 
- (prov) IntMath.java:313-367 — IntMath.divide(MIN_VALUE, -1, mode) silently returns MIN_VALUE instead of throwing ArithmeticEx

## greenrobot__EventBus  (Qwen 9 susp | Claude 2 | overlap 0 | Claude-only 2 | Qwen-only 9)


**Claude-only:**
- [med/med] `EventBus#hasSubscriberForEvent` — hasSubscriberForEvent ignores eventInheritance(false), returns true for events post() won't del
- [med/med] `BackgroundPoster#run` — executorRunning reset in unsynchronized finally; lost-wakeup leaves queued post with no executo

**Qwen-only:**
- (prov) SubscriberMethodFinder.java:271 — NullPointerException when traversing class hierarchy reaches Object.class, because clazz.getNam
- (prov) AbstractSubscriberInfo.java:48 — Using Class.newInstance() instead of Class.getDeclaredConstructor().newInstance() - deprecated 
- (refu) AsyncPoster.java:37 — In AsyncPoster, every enqueue creates a new thread execution but only processes one PendingPost
- (prov) BackgroundPoster.java:66 — InterruptedException is caught but thread interrupt status is not restored via Thread.currentTh
- (prov) Subscription.java:46 — Subscription.hashCode() throws NullPointerException if called before SubscriberMethod.equals() 
- (prov) EventBusBuilder.java:104 — EventBusBuilder.executorService(null) is accepted silently; later use in AsyncPoster.enqueue() 
- (refu) EventBus.java:49 — eventTypesCache uses plain HashMap and stores mutable ArrayLists; if lookupAllEventTypes return
- (inco) Subscription.java:34 — Subscription.equals uses identity comparison (==) for subscriber Object which is inconsistent w
- (prov) EventBus.java:443 — mainThreadPoster is potentially null on non-Android platforms, but postToSubscription for Threa

## jenkinsci__jenkins  (Qwen 9 susp | Claude 3 | overlap 2 | Claude-only 1 | Qwen-only 7)

**Overlap (both suspected):**
- `PackedMap#values` — C: values().get(index) reads kvpairs[index*2] (the key) instead of index*2+1 (the value) / Q: PackedMap.values() returns keys: uses index*2 (keys) not index*2+1 (values)
- `QuotedStringTokenizer#unquote` — C: \uXXXX escape decoded with byte shifts (24,16,8,0) instead of nibble shifts (12,8,4,0) / Q: unquote() wrong \uXXXX chars: 8-bit shifts instead of 4-bit nibble shifts

**Claude-only:**
- [low/hig] `FlightRecorderInputStream#skip` — skip() forwards read()'s -1 at EOF, violating InputStream#skip (never negative)

**Qwen-only:**
- (prov) FlightRecorderInputStream.java:108-111 — skip(long n) silently truncates large skip requests to 64KB, failing to skip the full requested
- (refu) HexDump.java:32 — HexDump.toHex always prints "f" for the high nibble of bytes >= 0x80 instead of the correct hex
- (inco) PrivateKeyProvider.java:145-156 — loadKey throws NoSuchElementException on line 156 because the iterable was already consumed by 
- (prov) OneShotEvent.java:84-89 — OneShotEvent.block(timeout) returns prematurely on spurious wakeup because it uses `if` instead
- (prov) CyclicGraphDetector.java:61-63 — CyclicGraphDetector.detectedCycle() produces a cycle path with a duplicate node because it push
- (refu) PlainCLIProtocol.java:96 — The FramedOutput.writeInt sends data.length-1 as the frame length, but the actual data sent inc
- (inco) Iterators.java:235-237 — Iterators.sequence(start, end, step) uses integer division for size calculation which truncates

## kestra-io__kestra  (Qwen 17 susp | Claude 3 | overlap 2 | Claude-only 1 | Qwen-only 15)

**Overlap (both suspected):**
- `State#failedThenRestarted` — C: failedThenRestarted() does size-2 lookup without guard; IOOBE with <2 histories when RESTARTED / Q: IndexOutOfBoundsException in failedThenRestarted() with <2 histories where current is RESTARTED
- `FailedResponseInterceptor#process` — C: !statusCodes.contains(code) inverts logic: fires on all codes except listed, so 200 treated as  / Q: Interceptor throws on codes NOT in the list, opposite of intended, treating other responses as 

**Claude-only:**
- [med/med] `MapUtils#flattenToNestedMap` — On key conflict 'continue' skips only one segment, injecting spurious sibling branch not droppi

**Qwen-only:**
- (prov) DateUtils.java:97 — The groupByType method will misclassify time spans: durations between 2-179 days will be classi
- (prov) MapUtils.java:135 — deepMerge can return maps where collections contain the same object references as the originals
- (prov) ListUtils.java:74 — Partitioning a list and then modifying the original list (or the partitions) can cause Concurre
- (prov) DefaultScheduler.java:253 — After exiting maintenance mode, TriggerSchedulingLoop instances have empty vNode assignments (c
- (prov) TaskRun.java:351 — Calling addAttempt mutates the original TaskRun instead of returning a new one. Code that expec
- (prov) VariableRenderer.java:194 — When rendering map keys, if two keys resolve to the same rendered string, the second key's valu
- (prov) State.java:47 — Calling withState() on a State object mutates the original State's histories list, causing shar
- (prov) EncryptionService.java:88 — Decryption with a ciphertext shorter than 12 bytes (the IV length) will throw an unhelpful Ille
- (prov) JacksonMapper.java:195 — ClassCastException when the first element of a JSON patch array is not an ObjectNode but the co
- (prov) VariableRenderer.java:213 — When renderObject is called with a Set containing non-String elements (e.g., Set<Integer>), the
- (prov) Pause.java:266 — NullPointerException in findTerminalState when the pause task's outputs don't contain a "resume
- (refu) HttpService.java:51 — Null pointer exception or invalid content type when copying an HTTP entity that doesn't have a 
- (refu) FlowableUtils.java:324 — readAndCountLoopValuesFromUri returns nextOffset as record count (result.size()) but the javado
- (prov) KvFunction.java:55 — NullPointerException in KvFunction when "flow" Pebble variable is null, causing the kv() functi
- (prov) ChunkFilter.java:38 — ChunkFilter with size 0 or negative throws unhandled IllegalArgumentException, and returns a vi

## keycloak__keycloak  (Qwen 37 susp | Claude 3 | overlap 1 | Claude-only 2 | Qwen-only 36)

**Overlap (both suspected):**
- `JsonWebToken#isIssuedBeforeSessionStart` — C: getIat()+1 auto-unboxes null Long, throwing NPE when iat claim is absent / Q: getIat() returns null Long when iat unset; getIat()+1 triggers auto-unboxing NPE

**Claude-only:**
- [hig/hig] `KeycloakModelUtils#escapeGroupNameForPath / splitPath` — Group path escape never escapes literal '~', so trailing '~' collides with '~/' marker
- [med/hig] `NetworkUtils#compactLongestZeroSequence / formatAddress6` — formatAddress6 compresses a single 16-bit zero field into '::', violating RFC 5952

**Qwen-only:**
- (prov) JsonSerialization.java:54 — Using `prettyMapper.writeValueAsString()` on objects containing Optional or Java 8 time types (
- (prov) KeycloakModelUtils.java:387 — NullPointerException when calling runOnRealm if the session's current realm context is null. Th
- (prov) HmacOTP.java:48 — The missing characters 'X', 'Y', 'Z' in the secret character set reduces the entropy of generat
- (prov) StringUtil.java:132 — When the string exactly equals the suffix, the suffix is not removed. `removeSuffix("foo", "foo
- (prov) JWSInput.java:47 — JWTs with empty signature field (algorithm 'none') using `header.content.` format would have th
- (prov) DerUtils.java:82 — The InputStream is closed unconditionally and not in a try-finally/try-with-resources block, ca
- (prov) DerUtils.java:52 — Using `DataInputStream.available()` to size the buffer is unreliable — if the stream has not ye
- (prov) XMLTimeUtil.java:182 — The null check in parseAsDuration is ineffective — it logs but doesn't return or throw, so the 
- (prov) UriUtils.java:104 — `stripQueryParam` does not escape `name` for regex usage. A parameter name containing regex met
- (refu) SecretGenerator.java:54 — When assertions are disabled (production default), `generateBase64SecureId` may return IDs cont
- (prov) ProtocolMapperUtils.java:128-130 — Empty string passed to `getLowerCasedProperty` causes `StringIndexOutOfBoundsException` instead
- (inco) JWSHeader.java:90-93 — `getRawAlgorithm()` will NPE when called on a JWSHeader with a null algorithm, which can happen
- (prov) IoUtils.java:33-41 — `readFromConsole` accepts empty passwords and can return null from `readLine` without validatio
- (prov) NetworkUtils.java:428-435 — `checkForPresence` uses the search `value` as the default in `System.getProperty(key, value)`, 
- (prov) OIDCRedirectUriBuilder.java:168-173 — XSS vulnerability: param names in FormPostRedirectUriBuilder are not HTML-escaped before being 
- (refu) Encode.java:210 — `userInfoStringEncoding` initialization uses platform default charset instead of UTF-8, causing
- (refu) DurationConverter.java:39-40 — Case-insensitive regex for MILLIS suffix doesn't account for case in substring extraction. Inpu
- (prov) KeystoreUtil.java:128 — NPE on line 128 when getCertificate returns null — the null check on line 129 for publicKey is 
- (refu) SessionExpirationUtils.java:112 — Client session max lifespan is incorrectly calculated as -1 (never expires) when user session d
- (prov) JWSBuilder.java:114-148 — Malformed JWT header JSON when header values (kid, x5t, type, contentType) contain unescaped do
- (prov) OctetStringEncoder.java:25 — NullPointerException: When `parameterValue` is null, `escapeAsString` calls `null.toString()`, 
- (inco) SPNEGOAuthenticator.java:169 — NullPointerException: `acceptSecContext` returns null when context is established with no respo
- (inco) StringPropertyReplacer.java:163-165 — When input stream ends with '$' character, the output incorrectly includes an extra 0xff byte i
- (prov) AccountConsole.java:176-177 — NoSuchElementException thrown when trying to read an empty theme resource file, and the Scanner
- (prov) FilterUtils.java:86-111 — The `unescapeJsonString` method does not handle JSON unicode escape sequences like `\uXXXX`. Wh
- (prov) LDAPQueryConditionsBuilder.java:71-74 — NullPointerException in `addCustomLDAPFilter` when `filter` parameter is null, because `filter.
- (prov) HmacOTP.java:80-91 — Integer overflow in `validateHOTP` loop when `counter` is close to `Integer.MAX_VALUE`, causing
- (prov) LDAPDn.java:239 — `StringIndexOutOfBoundsException` when calling `RDN.toString(false)` on an RDN with no attribut
- (prov) LDAPUtils.java:320-360 — ArrayIndexOutOfBoundsException or StringIndexOutOfBoundsException in `generalizedTimeToDate` wh
- (inco) LDAPContextManager.java:108-122 — Resource leak in `startTLS`: when `tls.negotiate()` fails, the `StartTlsResponse` is not closed
- (prov) CollectionUtil.java:41-61 — NullPointerException in `collectionEquals` when either collection parameter is null, because th
- (refu) RedirectUtils.java:162-178 — If `UriUtils.decodeQueryString(query)` throws an exception on malformed query strings (e.g., in
- (prov) Base64Url.java:36-39 — NullPointerException when `decode(null)` is called, as the method doesn't check for null input 
- (prov) TokenVerifier.java:127-137 — NullPointerException in `TokenTypeCheck.test` when `tokenTypes` list contains null entries, bec
- (prov) HtmlUtils.java:30-52 — NullPointerException when `escapeAttribute(null)` is called, as no null check is performed befo
- (inco) AbstractPairwiseSubMapper.java:100-102 — Method `setAccessTokenSubject` uses wrong parameter type `IDToken` instead of `AccessToken`, su

## libgdx__libgdx  (Qwen 14 susp | Claude 3 | overlap 3 | Claude-only 0 | Qwen-only 11)

**Overlap (both suspected):**
- `Polygon#getVertex` — C: getVertex bounds guard uses '>' not '>=', so vertexNum==count reads past array end (AIOOBE) / Q: getVertex(getVertexCount()) throws AIOOBE; check uses '>' instead of '>='
- `BinaryHeap#contains` — C: contains(node,false) loops full capacity not size, calls null.equals -> NPE on non-full heap / Q: contains(node,false) on non-full heap NPEs: for-each iterates nulls past size, calls .equals on
- `Rectangle#contains(Rectangle)` — C: contains(Rectangle) uses strict '>'/'<' so identical/edge-touching rects reported not contained / Q: contains(Rectangle) returns false when inner edges exactly touch outer, inconsistent w/ point s

**Qwen-only:**
- (prov) SnapshotArray.java:44 — Calling add() or addAll() on a SnapshotArray during an active snapshot (between begin() and end
- (prov) SortedIntList.java:62 — When inserting at an index that already has an element, insert() overwrites the old value witho
- (prov) SortedIntList.java:143 — Calling iterator.remove() on a SortedIntList leaks Node objects because the removed node is nev
- (prov) CharArray.java:356 — Calling numChars with radix 1 causes an infinite loop since value /= 1 never changes value, so 
- (refu) OrderedSet.java:117 — Not actually a bug after more careful analysis - the alter method correctly handles the transit
- (refu) IntSet.java:121 — Missing parentheses in 'i + 1 & mask' causes linear probing to not wrap around the table, leadi
- (prov) BSpline.java:54 — BSpline.cubic_derivative(T, float, T[], boolean, T) returns the curve value instead of the deri
- (prov) MathUtils.java:180 — MathUtils.nextPowerOfTwo(Integer.MAX_VALUE) returns Integer.MIN_VALUE instead of a valid power 
- (prov) IntArray.java:305 — IntArray.pop() and IntArray.peek() crash with ArrayIndexOutOfBoundsException on empty array ins
- (prov) Polygon.java:161 — Polygon.scale() uses addition instead of multiplication, producing wrong scale transformations.
- (prov) Matrix4.java:76 — Static temp objects in Matrix4 cause data corruption when multiple Matrix4 instances share comp

## mybatis__mybatis-3  (Qwen 25 susp | Claude 2 | overlap 1 | Claude-only 1 | Qwen-only 24)

**Overlap (both suspected):**
- `Reflector#getSetterType` — C: getSetterType NPEs on missing setter and prints shadowed null 'clazz' in error msg / Q: getSetterType uses shadowed local clazz in error msg; setTypes.get(prop) null -> NPE before err

**Claude-only:**
- [low/med] `ParamNameResolver#getType` — getType maps paramN via names.get(N-1) as key not ordinal; wrong type when special param preced

**Qwen-only:**
- (prov) PooledDataSource.java:337 — The bad connection tolerance check incorrectly adds poolMaximumIdleConnections to poolMaximumLo
- (prov) ParamNameResolver.java:110-128 — When there is only one non-special parameter but the first parameter of the method is a special
- (inco) PropertyNamer.java:41 — PropertyNamer.methodToProperty fails to properly handle methods like getXMLElement() where the 
- (prov) BaseExecutor.java:223-226 — The operator precedence issue with && and || causes the second condition to be evaluated regard
- (refu) ParameterMappingTokenHandler.java:158 — The instanceof Type check at line 158 is dead code since the return type of getType() is alread
- (prov) MapperBuilderAssistant.java:169 — The equals method in ResultMapping only compares by property name, so when a child resultMap ov
- (prov) DefaultResultSetHandler.java:707-708 — The cache key for pending child relations is created incorrectly — it uses the column name for 
- (prov) PerpetualCache.java:68-70 — The equals method in PerpetualCache violates the reflexive contract of equals(). When getId() r
- (prov) VFS.java:58-59 — The VFS.createVFS() for loop has no bounds check on index i. If all VFS implementations fail is
- (prov) DefaultVFS.java:341 — isJar() may return false for valid JAR files when the InputStream.read() doesn't read all 4 byt
- (prov) LoggingCache.java:34 — If the delegate cache has a null ID, LogFactory.getLog(null) is called in the constructor, whic
- (prov) BlockingCache.java:68-74 — If a cache miss occurs and the subsequent database query returns null, putObject is never calle
- (inco) BlockingCache.java:82 — BlockingCache.removeObject() never delegates to the underlying cache, so it fails to actually r
- (refu) ScheduledCache.java:60 — When ScheduledCache.get() finds the cache stale, it returns null unconditionally, discarding wh
- (inco) PropertyTokenizer.java:30 — PropertyTokenizer splits property names on the first dot even if it's inside brackets, causing 
- (prov) ArrayTypeHandler.java:92 — Primitive arrays (int[], long[], double[], etc.) cannot be cast to Object[], so ArrayTypeHandle
- (refu) DefaultResultSetHandler.java:977 — Re-examining: the column prefix is uppercased in getColumnPrefix but the actual column matching
- (prov) FifoCache.java:77-83 — FifoCache accumulates duplicate keys in its deque when the same key is put multiple times, caus
- (prov) BatchExecutor.java:62 — BatchExecutor.doUpdate uses `sql.equals(currentSql)` where sql could be null if the BoundSql ha
- (inco) PooledConnection.java:224 — PooledConnection.equals() at line 224 calls realConnection.hashCode() without null check, which
- (inco) UnpooledDataSource.java:257 — UnpooledDataSource.configureConnection() creates a new single-thread ExecutorService on every c
- (inco) OgnlCache.java:38 — OgnlCache.expressionCache is an unbounded static ConcurrentHashMap that never evicts entries, c
- (prov) ForEachSqlNode.java:72 — ForEachSqlNode.apply() calls iterable.iterator().hasNext() just to check emptiness, then discar
- (prov) BlockingCache.java:63 — BlockingCache.putObject() always throws IllegalStateException because it tries to release a loc

## netty__netty  (Qwen 31 susp | Claude 12 | overlap 5 | Claude-only 7 | Qwen-only 26)

**Overlap (both suspected):**
- `AppendableCharSequence#charAt(int)` — C: charAt bounds check 'index > pos' should be 'index >= pos'; charAt(pos) reads stale tail char / Q: charAt bounds check 'index > pos' should be 'index >= pos'; chars[pos] out of bounds
- `AppendableCharSequence#substring(int,int)` — C: substring guard 'length > pos' fails to reject end>pos when start>=1; reads stale tail / Q: substring bounds check 'length > pos' should be 'start + length > pos'; reads beyond valid data
- `ProtobufVarint32FrameDecoder#readRawVarint40` — C: With exactly 4 continuation-bit bytes, throws CorruptedFrameException instead of waiting for 5t / Q: Throws CorruptedFrameException for incomplete 5-byte varint when 4 bytes have continuation bits
- `SmtpResponseDecoder#newDecoderException` — C: newDecoderException uses frame's indices but reads from raw buffer, echoing wrong region / Q: newDecoderException passes frame indices but reads from original input buffer, garbage message
- `StompSubframeDecoder#decode (READ_CONTENT)` — C: (int)(contentLength - alreadyRead) overflows negative for content-length > Integer.MAX_VALUE / Q: Casts large long contentLength to int for remainingLength, integer overflow / negative remainin

**Claude-only:**
- [hig/hig] `AsciiString#trim(CharSequence)` — Static trim on generic CharSequence passes inclusive end as exclusive to subSequence, drops las
- [med/hig] `MpscIntQueue.MpscAtomicIntegerArrayQueue#weakPeekReduce(int,int,IntBinaryOperator)` — weakPeekReduce returns 0 instead of the initial seed when limit==0
- [low/med] `HttpObjectDecoder static init of ISO_CONTROL_OR_WHITESPACE / LATIN_WHITESPACE` — Table-fill loop 'b < Byte.MAX_VALUE' skips index 127 (DEL), leaving DEL unflagged as control
- [med/hig] `MqttReasonCodes#valueOfHelper` — valueOfHelper returns null for in-range-but-empty sparse index instead of throwing IAE
- [low/hig] `MqttProperties.MqttProperty#equals / #hashCode (as inherited by BinaryProperty)` — BinaryProperty inherits equals/hashCode using byte[] identity instead of content
- [med/hig] `SmtpResponseDecoder#decode` — Min-length guard 'readable < 3' should be < 4; a 3-byte line makes readByte throw IOOBE
- [med/hig] `SmtpResponseDecoder#parseNumber / parseCode` — parseNumber returns -1 for non-digit bytes; parseCode never validates, yielding wrong/negative 

**Qwen-only:**
- (prov) LongLongHashMap.java:60-66 — LongLongHashMap.put() may return the wrong previous value when a key is re-inserted because the
- (refu) ServerCookieDecoder.java:140 — ServerCookieDecoder incorrectly sets valueBegin and valueEnd to 0 instead of i (headerLen) when
- (prov) ServerCookieDecoder.java:100 — When parsing an RFC2965-style cookie header without any semicolons (e.g., just "$Version"), ind
- (prov) ServerCookieDecoder.java:161-163 — When an RFC2965-style cookie header contains attributes with different casing like '$path' or '
- (prov) XmlFrameDecoder.java:94-99 — XmlFrameDecoder incorrectly uses writerIndex instead of readableBytes for maxFrameLength check,
- (refu) HAProxyMessageDecoder.java:209 — No issue found after careful review - the indices are handled correctly.
- (prov) RedisDecoder.java:334 — Long overflow in Redis positive number parser produces silently wrong negative results for vali
- (prov) ServerCookieEncoder.java:106 — Overflow in expires date computation for large maxAge values causes the Set-Cookie Expires head
- (refu) ServerCookieEncoder.java:225 — Not actually a bug - the logic handles edge cases correctly. Moving on.
- (prov) MqttDecoder.java:897 — MqttDecoder reads unsigned 4-byte MQTT property values (PUBLICATION_EXPIRY_INTERVAL, SESSION_EX
- (refu) MarshallingDecoder.java:76 — MarshallingDecoder leaks the ByteBuf frame reference by not calling frame.release() after using
- (prov) MarshallingDecoder.java:84 — MarshallingDecoder.extractFrame() returns buffer.slice() instead of buffer.retainedSlice(), bre
- (refu) LongLongHashMap.java:132 — LongLongHashMap.computeMaskAndProbe has incorrect operator precedence in `mask = length - 1 & M
- (refu) Lz4Constants.java:58 — Lz4Constants.MAX_BLOCK_SIZE has incorrect operator precedence: `1 << COMPRESSION_LEVEL_BASE + 0
- (prov) MqttDecoder.java:268 — MqttDecoder.decodeProperties loop starts numberOfBytesConsumed at the varint prefix length inst
- (refu) MqttDecoder.java:868 — In decodeProperties, SUBSCRIPTION_IDENTIFIER (case at line 902) only decodes a single Variable 
- (prov) JsonObjectDecoder.java:206 — In JsonObjectDecoder.decodeByte, the backslash scanning loop (line 206) checks `idx >= 0` but s
- (refu) ServerCookieDecoder.java:147 — ServerCookieDecoder uses `semiPos > 0` instead of `semiPos >= 0` to check if indexOf found the 
- (prov) AppendableCharSequence.java:95 — AppendableCharSequence.append(CharSequence, int start, int end) does not validate that start >=
- (prov) RedisDecoder.java:298 — RedisDecoder.readLine() computes slice length as lfIndex - readerIndex - 1. If lfIndex equals r
- (refu) ServerCookieDecoder.java:161 — ServerCookieDecoder uses String.regionMatches without verifying that the remaining header lengt
- (prov) HAProxyMessageDecoder.java:344 — HAProxyMessageDecoder.StructHeaderExtractor.findEndOfHeader returns a relative length (totalHea
- (refu) Base64.java:161 — The e offset tracking and newline removal logic in Base64.encode may have an off-by-one error w
- (prov) ByteBufUtil.java:243 — ByteBufUtil.indexOf(ByteBuf needle, ByteBuf haystack) returns 0 for empty needle but should ret
- (prov) ObjectUtil.java:122 — ObjectUtil.checkPositive(double) and checkPositive(float) do not reject NaN values because NaN 
- (refu) Unpooled.java:177 — Unpooled.wrappedBuffer(byte[], int, int) creates an intermediate UnpooledHeapByteBuf via wrappe

## redisson__redisson  (Qwen 10 susp | Claude 2 | overlap 2 | Claude-only 0 | Qwen-only 8)

**Overlap (both suspected):**
- `RedissonTransactionalBucket#isEquals` — C: isEquals finally calls readableBytes() not release(), leaking 2 encoded ByteBufs per CAS / Q: isEquals ByteBuf leak: readableBytes() called instead of release() in finally, leaks per CAS
- `RedissonSetMultimap#fastRemoveValueAsync` — C: fastRemoveValueAsync Lua returns hardcoded 0 instead of accumulated size; count always 0 / Q: fastRemoveValueAsync always returns 0 because Lua hardcodes 'return 0;' instead of 'return size

**Qwen-only:**
- (prov) RedissonTransaction.java:545 — Using wrong batch variable `batch` instead of `publishBatch` on line 545 causes the setCache.re
- (prov) BaseRedissonList.java:222 — The comparison `== 1` for LREM return value is wrong; it should be `> 0` since LREM can remove 
- (inco) RedissonCache.java:184 — The async retrieve method cannot distinguish between a cache miss and a cached null value, caus
- (inco) RedissonBlockingQueue.java:75 — The offer(e, timeout, unit) method ignores timeout parameters and calls non-blocking offer(e) i
- (inco) RedissonBloomFilter.java:123 — Division by zero when addAsync is called with an empty collection. The code at line 123 divides
- (refu) RedissonScoredSortedSet.java:80 — RedissonScoredSortedSet.readAllAsync() always returns an empty collection because valueRangeAsy
- (refu) RedissonSetMultimapCache.java:53 — RedissonSetMultimapCache.containsKeyAsync has a ByteBuf leak - keyState is never released, caus
- (inco) RedissonScoredSortedSet.java:363 — pollLastFromAny(int, String...) returns the FIRST (MIN score) elements instead of the LAST (MAX

## skylot__jadx  (Qwen 4 susp | Claude 3 | overlap 1 | Claude-only 2 | Qwen-only 3)

**Overlap (both suspected):**
- `ImmutableList#lastIndexOf` — C: lastIndexOf loop `i > 0` skips index 0, returns -1 for element only at index 0 / Q: lastIndexOf skips index 0 (`i > 0` vs `i >= 0`), returns -1 for element at position 0

**Claude-only:**
- [med/hig] `ImmutableList#equals` — equals asymmetric; ArrayList.equals(immutableList) calls listIterator() which throws UOE
- [med/med] `TypeCompare.ArgTypeComparator#compare` — compare maps symmetric CONFLICT to -2 both directions, breaking antisymmetry (TimSort crash)

**Qwen-only:**
- (refu) StringFormattedCheck.java:88 — IndexOutOfBoundsException when parsing format strings ending with digits after %d (e.g., "%d5" 
- (prov) Utils.java:44,54 — StringIndexOutOfBoundsException when either cleanObjectName or cutObject is called with an empt
- (prov) TypeCompare.java:88-89 — When comparing two unknown types with same number of possible types, TypeCompare incorrectly re

## spring-projects__spring-boot  (Qwen 25 susp | Claude 2 | overlap 1 | Claude-only 1 | Qwen-only 24)

**Overlap (both suspected):**
- `TypeUtils$TypeDescriptor#resolveGeneric` — C: resolveGeneric guard only blocks 1-node cycle; A->B->A causes infinite recursion / SOE / Q: resolveGeneric() no protection against indirect cycles, infinite recursion with A->B->A

**Claude-only:**
- [med/hig] `TypeUtils#paramJavadocPattern` — @param javadoc regex lacks word boundary; component name prefix matches wrong @param line

**Qwen-only:**
- (inco) Instantiator.java:192 — When instantiation of a type fails, the resulting null value in the stream will cause NPE durin
- (inco) SpringBootCondition.java:78 — ClassCastException when AnnotatedTypeMetadata is neither ClassMetadata nor MethodMetadata - the
- (inco) LambdaSafe.java:173 — ClassCastExceptions with null messages are incorrectly treated as lambda generic type problems 
- (inco) CertificateMatcher.java:50 — CertificateMatcher stores and reuses a single `Signature` instance across multiple `verify()` c
- (prov) SimpleConfigurationMetadataRepository.java:76 — Calling `add(property, source)` with a source whose groupId hasn't been registered will cause a
- (inco) AggregateBinder.java:115 — AggregateSupplier.wasSupplied() cannot distinguish between 'supplier not yet called' and 'suppl
- (inco) BindConverter.java:60 — The shared BindConverter instance is used concurrently from multiple threads during property bi
- (inco) OnExpressionCondition.java:69 — When a SpEL expression in @ConditionalOnExpression evaluates to a non-Boolean non-null value (e
- (refu) ConfigurationPropertyName.java:167-170 — ConfigurationPropertyName is used as a key in ConcurrentHashMap caches but has lazy mutable ini
- (refu) NoUnboundElementsBindHandler.java:149-156 — When getIndexed() encounters a numeric index at the last position (e.g., 'my.list[0]'), it call
- (inco) ArrayBinder.java:51 — ArrayBinder.bindAggregate calls Array.newInstance(elementType.resolve(), list.size()) where ele
- (inco) OnClassCondition.java:129-137 — OnClassCondition.addAll() blindly casts annotation attribute values to String[] but Conditional
- (inco) Bindable.java:143-161 — Bindable.equals() compares type.resolve() (raw class) while hashCode() uses the full Resolvable
- (refu) ValueObjectBinder.java:274-287 — KotlinValueObject.parseConstructorParameters() iterates over ALL KFunction parameters including
- (inco) PeriodStyle.java:86-95 — PeriodStyle.SIMPLE.print() does not include weeks in the output, causing loss of format informa
- (prov) DockerCli.java:47 — DockerCli.dockerCommandsCache is a non-thread-safe HashMap used with computeIfAbsent in a poten
- (inco) OnResourceCondition.java:73-74 — OnResourceCondition.collectValues() throws ClassCastException when resources attribute contains
- (inco) ConfigurationPropertyName.java:527-538 — ConfigurationPropertyName.hashCode() recomputes hash on every call when the hash legitimately e
- (inco) MapBinder.java:117-120 — MapBinder.merge() creates new map with wrong type and wrong capacity hint in exception path.
- (refu) BindResult.java:41-157 — BindResult cannot distinguish between "no value bound" and "null value bound" - null values are
- (inco) DefaultConnectionPorts.java:48-54 — DefaultConnectionPorts.portMappings loses protocol distinction when same port number has both T
- (refu) ExplodedArchive.java:63 — ExplodedArchive constructor throws NPE because it accesses rootDirectory field before assignmen
- (inco) FileWatcher.java:127-138 — FileWatcher.collectRegistrationPaths() causes StackOverflowError when following cyclic symlinks
- (inco) DockerHost.java:112-114 — DockerHost.fromEndpoint() throws uncaught IllegalArgumentException for malformed DOCKER_HOST UR

## thingsboard__thingsboard  (Qwen 41 susp | Claude 2 | overlap 2 | Claude-only 0 | Qwen-only 39)

**Overlap (both suspected):**
- `SchedulerUtils#getStartOfCurrentHour` — C: getStartOfCurrentHour reinterprets UTC wall-time as zoneId, shifting instant by the zone offset / Q: SchedulerUtils mixes UTC LocalDateTime/LocalDate with arbitrary ZoneId, wrong epoch ms for non-
- `MqttChannelHandler#handlePubrec` — C: handlePubrec dereferences pendingPublish from map get() without null check, NPE on unknown PUBR / Q: MqttChannelHandler.handlePubrec() NPE when pendingPublish is null

**Qwen-only:**
- (inco) GeoUtil.java:72 — Point coordinates are swapped (lat/lon vs lon/lat) in the contains() method, causing incorrect 
- (inco) ExpressionUtils.java:29 — Public mutable static ArrayList allows external code to corrupt the shared function registry, c
- (pend) ReconnectStrategyExponential.java:59 — calculateJitter() returns 0 or 1 (second) but the variable naming suggests nanosecond jitter, c
- (inco) JacksonUtil.java:353 — StringIndexOutOfBoundsException when node.toString() returns a string shorter than 20 character
- (inco) MultipleTbQueueCallbackWrapper.java:42 — MultipleTbQueueCallbackWrapper.onFailure ignores the counter, causing the main callback to be i
- (inco) TbQueueConsumerManagerTask.java:69 — DeletePartitionsTask.getType() incorrectly returns QueueTaskType.REMOVE_PARTITIONS instead of a
- (inco) SystemUtil.java:104 — ArithmeticException (divide by zero) in SystemUtil.toPercent() when total memory or disk space 
- (inco) GeoUtil.java:196 — ClassCastException in GeoUtil.containsArrayWithPrimitives() when the JsonArray contains non-arr
- (inco) TbActorMailbox.java:161 — TbActorMailbox.processMailbox() continues processing after destroy() call, and never resets bus
- (inco) TbCheckMessageNode.java:127 — ClassCastException in TbCheckMessageNode.dataToMap() when message data is not a JSON object, or
- (inco) AlarmRuleState.java:198-206 — AlarmRuleState.isActive() has off-by-one bug where midnight (msFromStartOfDay==0) is excluded w
- (inco) TbCoapClientState.java:135 — TbCoapClientState.addQueuedNotification() merges msg.getSharedDeletedList() twice and drops mis
- (inco) EncryptionUtil.java:63 — EncryptionUtil.getSha3Hash() uses platform-default charset via getBytes() instead of UTF-8, pro
- (inco) MqttPendingPublish.java:70 — MqttPendingPublish leaks ByteBuf memory: retransmissionHandler calls payload.retain() on each r
- (refu) TbRestApiCallNode.java:110-115 — TbRestApiCallNode.upgrade() switch fall-through may remove properties added by earlier cases si
- (inco) TbSaveToCustomCassandraTableNode.java:182 — TbSaveToCustomCassandraTableNode uses string-based contains(".") to distinguish long vs double,
- (prov) GeoUtil.java:194-202 — GeoUtil.containsArrayWithPrimitives returns true for empty JsonArray, causing createPolygon to 
- (prov) GeoUtil.java:186-192 — GeoUtil.containsPrimitives() only checks first element instead of all elements, allowing malfor
- (inco) TbRenameKeysNode.java:74-84 — TbRenameKeysNode silently overwrites existing keys when multiple rename mappings target the sam
- (inco) RepositoryUtils.java:70-74 — RepositoryUtils.SORT_DESC reverses the ID tiebreaker comparator along with the primary sort, ca
- (inco) KafkaTbQueueMsg.java:33-38 — KafkaTbQueueMsg constructor NPE on null key and IllegalArgumentException on keys shorter than 3
- (inco) MultipleTbMsgsCallbackWrapper.java:40-43 — MultipleTbMsgsCallbackWrapper.onFailure() doesn't decrement counter, allowing both onSuccess an
- (inco) TbMsg.java:209-210 — TbMsg.getMetaDataTs() NPE when metaData field is null
- (inco) MqttClientImpl.java:192-199 — MqttClientImpl message ID wraps prematurely at 65534, reusing ID 1 while pending messages with 
- (prov) MqttChannelHandler.java:310 — ReferenceCountUtil.release(cause) passes a Throwable instead of a ReferenceCounted object, maki
- (refu) TemplateUtils.java:43-44 — TemplateUtils.processTemplate() adds spurious backslash to unresolved template variables in out
- (inco) RedisTbTransactionalCache.java:166-178 — RedisTbTransactionalCache.evictOrPut() skips putting the new value when the old key existed, le
- (inco) CaffeineTbTransactionalCache.java:104-107 — CaffeineTbTransactionalCache.evictOrPut() ignores the new value parameter entirely, never putti
- (inco) TbCheckMessageNode.java:121-123 — TbCheckMessageNode.metadataToMap() NPE when TbMsg has null metaData
- (inco) GeoUtil.java:150-158 — GeoUtil.buildPolygonFromCoordinates() mutates its input list via coordinates.clear(), causing s
- (inco) BaseMonitoringService.java:203-208 — BaseMonitoringService.check() destroys parent health checker instead of stale associate when re
- (inco) MqttTransportHandler.java:265 — MqttTransportHandler.sendSuccessRpcResponse() sets the success payload via setError() on protob
- (inco) TbNodeUtils.java:115-121 — TbNodeUtils.processTemplate() re-expands template patterns in already-substituted values, causi
- (refu) SetCache.java:40 — SetCache.contains() may return true for expired entries since asMap().containsKey() does not tr
- (inco) RedisTbTransactionalCache.java:201-214 — RedisTbTransactionalCache.getConnection() leaks Jedis connections from the pool by borrowing vi
- (inco) HashPartitionService.java:274 — HashPartitionService.resolveByPartitionIdx() may throw NoSuchElementException when accessing te
- (refu) DefaultTbActorSystem.java:201 — DefaultTbActorSystem.stop(actorId) can cause ConcurrentModificationException when recursively s
- (inco) TbMsgCountNode.java:72 — TbMsgCountNode delta calculation is incorrect - it adds delay to compensate for pre-incremented
- (inco) MqttClientImpl.java:73 — MqttClientImpl uses non-thread-safe HashSet and HashMultimap for serverSubscriptions, pendingSu

## zxing__zxing  (Qwen 14 susp | Claude 1 | overlap 1 | Claude-only 0 | Qwen-only 13)

**Overlap (both suspected):**
- `ECIStringBuilder#appendCharacters` — C: appendCharacters NPEs when called on fresh builder because 'result' is still null / Q: appendCharacters() NPE: result is null, never initialized before result.append(value)

**Qwen-only:**
- (prov) BitMatrix.java:485 — BitMatrix.hashCode() violates equals/hashCode contract: two BitMatrices with same width, height
- (refu) BitArray.java:170 — BitArray.setRange() and isRange() produce an incorrect mask when lastBit=31 (the 32nd bit), cau
- (prov) FinderPatternFinder.java:290 — haveMultiplyConfirmedCenters() divides totalModuleSize by max (total candidates) instead of con
- (prov) RSS14Reader.java:463 — Line 463 calls `increment(getEvenCounts(), getOddRoundingErrors())` passing odd rounding errors
- (refu) FieldParser.java:105-109 — The THREE_DIGIT_PLUS_DIGIT_DATA_LENGTH map uses 3-digit keys (e.g., "310") for AIs that actuall
- (refu) CharacterSetECI.java:111 — Calling `getCharset()` on enum values like ISO8859_2, ISO8859_3, etc. will throw UnsupportedCha
- (prov) PDF417ScanningDecoder.java:199 — PDF417 metadata comparison uses && instead of ||, so left and right metadata can have mismatche
- (prov) BufferedImageLuminanceSource.java:48 — BufferedImageLuminanceSource allows invalid crop rectangle for TYPE_BYTE_GRAY images, causing A
- (prov) DecodedBitStreamParser.java:195 — QR Code GB2312 subset decoding uses wrong threshold on assembledTwoBytes instead of original tw
- (refu) RSS14Reader.java:117 — RSS14Reader constructResult uses i > 0 instead of i >= 0 in leading zero padding loop, producin
- (prov) UPCEANExtension5Support.java:113 — UPCEANExtension5Support extensionChecksum multiplies both odd and even position sums by 3 inste
- (prov) PDF417CodewordDecoder.java:68,72 — bitCountIndex can exceed the bounds of moduleBitCount/result arrays (size 8) when the condition
- (prov) DefaultPlacement.java:83,86 — DefaultPlacement encoder corner3/corner4 conditions are swapped relative to BitMatrixParser dec