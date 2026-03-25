.PHONY: build run clean smoke-test

JAVA_FILE=src/main/java/com/example/tenthman/TenthManPlannerServer.java
OUT_DIR=out
MAIN_CLASS=com.example.tenthman.TenthManPlannerServer

build:
	javac --release 21 -d $(OUT_DIR) $(JAVA_FILE)

run: build
	java -cp $(OUT_DIR) $(MAIN_CLASS)

smoke-test: build
	bash scripts/smoke_test.sh

clean:
	rm -rf $(OUT_DIR)
