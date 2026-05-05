import sys

print("PYLEVELUP_MAIN_ENTERED", flush=True)

try:
    from pylevelup.bot import main
except Exception as exc:
    print(f"PYLEVELUP_IMPORT_FAILED: {type(exc).__name__}: {exc}", flush=True)
    raise

if __name__ == "__main__":
    print("PYLEVELUP_MAIN_CALLING", flush=True)
    try:
        main()
    except SystemExit:
        raise
    except BaseException as exc:
        print(f"PYLEVELUP_MAIN_CRASHED: {type(exc).__name__}: {exc}", flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)
